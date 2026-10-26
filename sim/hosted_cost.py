"""Conservative local spending stop for the authorized NVIDIA live trial.

This is a controller account, not a provider invoice. Missing usage keeps the
full reservation charged against the ceiling so another run cannot spend it.
"""
from __future__ import annotations

from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get('SIM_PROVIDER_ROOT', str(Path.home() / '.local/state/sim-provider')))
PRIOR = ROOT / 'hosted-spend.json'
RECORD = ROOT / 'nvidia-live-cost.json'
LIMIT = Decimal(os.environ.get('SIM_PROVIDER_CAP_USD', '10'))
MODEL = 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'
INPUT_RATE = Decimal('0.06')
OUTPUT_RATE = Decimal('0.24')
PRICE_SOURCE = 'https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference'
MAX_PROMPT_BYTES = 60000
MAX_OUTPUT_TOKENS = 1024
NANO = {'input': INPUT_RATE, 'output': OUTPUT_RATE, 'prompt_bytes': MAX_PROMPT_BYTES, 'output_tokens': MAX_OUTPUT_TOKENS,
        'image_tokens': 0, 'id_verified': True}
# P1 judge: Nemotron 3.5 Super VL 120B-A12B. Rates from PRICE_SOURCE, read 17 Oct 2026. The ID was read from the
# live Token Factory /v1/models list with the account key on 17 Oct 2026 (orchestrator relay; this lane had no key).
# The image-token price is not on the page; image_tokens is our own allowance, charged at the input rate.
# P1 is off unless the operator sets JUDGE_MODEL_ENV to exactly this ID.
JUDGE_MODEL = 'nvidia/Nemotron-3.5-Super-VL'
JUDGE_MODEL_ENV = 'TOKEN_FACTORY_JUDGE_MODEL'
SUPER_VL = {'input': Decimal('0.30'), 'output': Decimal('0.90'), 'prompt_bytes': 12000, 'output_tokens': 256,
            'image_tokens': 3000, 'id_verified': True, 'id_source': 'Token Factory /v1/models, 17 Oct 2026'}
# The review shop uses Ultra for the two jobs where a larger reasoning model pays
# for itself: planning a bounded batch and deciding whether a candidate finding
# is a product defect. The exact id was read from this account's /v1/models list
# on 24 Oct 2026. Rates were checked against the Nebius Nemotron catalog on the
# same date. Ultra receives text evidence only; Super VL remains the screen judge.
ULTRA_MODEL = 'nvidia/Nemotron-3-Ultra-550b-a55b'
ULTRA = {'input': Decimal('1.00'), 'output': Decimal('3.00'), 'prompt_bytes': 30000, 'output_tokens': 512,
         'image_tokens': 0, 'id_verified': True, 'id_source': 'Token Factory /v1/models, 24 Oct 2026'}


def money(value):
    return Decimal(str(value))


def prior_total():
    return sum((money(row['committed_usd']) for row in json.loads(PRIOR.read_text())['runs']), Decimal(0))


def judge_model():
    model = os.environ.get(JUDGE_MODEL_ENV, '').strip() or None
    if model is not None and model != JUDGE_MODEL:
        raise ValueError(f'The judge must be the registered {JUDGE_MODEL}. Unset {JUDGE_MODEL_ENV} to run without a judge.')
    return model


def rates(model):
    if model == MODEL: return NANO
    if model == JUDGE_MODEL and judge_model() == JUDGE_MODEL: return SUPER_VL
    if model == ULTRA_MODEL: return ULTRA
    raise ValueError('The USD stop is priced only for the exact registered Nemotron Nano model and the operator-set judge model.')


def worst_case(calls, model=MODEL):
    if type(calls) is not int or calls < 1 or calls > 600:
        raise ValueError('Choose a bounded positive model-call count.')
    r = rates(model)
    # Ten times the published rate is reserved. UTF-8 bytes upper-bound
    # ordinary input token counts; the output has a provider request cap.
    return Decimal(calls) * ((Decimal(r['prompt_bytes']) + r['image_tokens']) * r['input'] +
                              Decimal(r['output_tokens']) * r['output']) * 10 / Decimal(1_000_000)


def projected(calls, model):
    reserve = worst_case(calls, model)
    return {'limit_usd': float(LIMIT), 'prior_controller_usd': float(prior_total()),
            'reserved_upper_usd': float(reserve), 'price_source': PRICE_SOURCE,
            'price_basis': '10 times listed token rates; not a provider billing cap or invoice'}


def _locked(update):
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(RECORD, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'r+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        raw = stream.read()
        data = json.loads(raw) if raw else {'schema': 'nvidia-live-cost/1', 'runs': {}}
        value = update(data)
        stream.seek(0)
        stream.truncate()
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
        return value


def reserve(identifier, calls, model):
    plan = projected(calls, model)
    amount = money(plan['reserved_upper_usd'])
    def write(data):
        if identifier in data['runs']:
            raise ValueError('This hosted trial already has a cost reservation.')
        committed = sum((money(row['accounted_usd']) for row in data['runs'].values()), Decimal(0))
        if prior_total() + committed + amount > LIMIT:
            raise ValueError('NVIDIA hosted inference would exceed the authorized USD 10 controller ceiling.')
        r = rates(model)
        data['runs'][identifier] = {'model': model, 'max_calls': calls,
                                   'input_rate': str(r['input']), 'output_rate': str(r['output']),
                                   'reserved_upper_usd': float(amount),
                                   'accounted_usd': float(amount), 'status': 'reserved',
                                   'price_source': PRICE_SOURCE}
        return {**plan, 'accounted_total_upper_usd': float(prior_total() + committed + amount)}
    return _locked(write)


def settle(identifier, usage, complete):
    def write(data):
        row = data['runs'][identifier]
        prompt = usage.get('prompt_tokens')
        output = usage.get('completion_tokens')
        if complete and type(prompt) is int and type(output) is int and prompt >= 0 and output >= 0:
            # Rows written before per-role pricing carry no rates; they were all Nano.
            measured = (Decimal(prompt) * Decimal(row.get('input_rate', INPUT_RATE)) +
                        Decimal(output) * Decimal(row.get('output_rate', OUTPUT_RATE))) / Decimal(1_000_000)
            if measured > money(row['reserved_upper_usd']):
                row['status'] = 'over_reservation_stop'
                row['accounted_usd'] = float(measured)
                row['usage'] = {'prompt_tokens': prompt, 'completion_tokens': output}
                row['stop_reason'] = 'Provider usage exceeded the conservative reservation; stop further hosted runs.'
                return dict(row)
            row['accounted_usd'] = float(measured)
            row['status'] = 'usage_accounted'
            row['usage'] = {'prompt_tokens': prompt, 'completion_tokens': output}
        else:
            row['status'] = 'unknown_usage_reservation_held'
        return dict(row)
    return _locked(write)
