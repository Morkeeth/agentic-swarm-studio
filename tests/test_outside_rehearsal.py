import json
import sys
from types import SimpleNamespace

import pytest

from sim import outside_rehearsal


@pytest.fixture
def portable_tools(monkeypatch):
    """Exercise the rehearsal contract without requiring developer CLIs on the test host."""
    real = outside_rehearsal.run
    def run(command, cwd):
        task = next((task for task in outside_rehearsal.TASKS if command[0] == task['command']), None)
        if task:
            return {'returncode': 0, 'output': task['expected']}
        return real(command, cwd)
    monkeypatch.setattr(outside_rehearsal, 'run', run)
    monkeypatch.setattr(outside_rehearsal.shutil, 'which', lambda command: '/test-bin/' + command)


def test_three_public_no_docker_tools_have_checked_tasks(tmp_path, portable_tools):
    roots = outside_rehearsal.fixtures(tmp_path)
    assert {task['id'] for task in outside_rehearsal.TASKS} == {'git', 'ripgrep', 'jq'}
    for task in outside_rehearsal.TASKS:
        observed = outside_rehearsal.run([task['command'], *task['canonical']], roots[task['id']])
        assert observed == {'returncode': 0, 'output': task['expected']}
        assert task['source'].startswith('https://github.com/')


def test_model_action_is_only_a_bounded_argument_array():
    assert outside_rehearsal.parse_args('{"args":["-n","ERROR_TOKEN","."]}', 'ripgrep') == ['-n', 'ERROR_TOKEN', '.']
    for raw in ('{"args":["-n","ERROR_TOKEN",";","rm"]}', '{"args":["--pre","cat","ERROR_TOKEN","."]}',
                '{"args":["/etc/passwd"]}', '{"args":"-n"}', '{"args":[]}', '{"args":[],"claim":true}', 'not json'):
        with pytest.raises((ValueError, json.JSONDecodeError)):
            outside_rehearsal.parse_args(raw, 'ripgrep')


def test_fresh_provider_attempts_create_exactly_three_result_cards(tmp_path, monkeypatch, portable_tools):
    model = 'nvidia/test-nemotron'
    monkeypatch.setenv('TOKEN_FACTORY_MODEL', model)
    calls = []

    class Client:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]['content']
            task = next(task for task in outside_rehearsal.TASKS if task['task'] in prompt)
            calls.append((task['id'], kwargs))
            return SimpleNamespace(model=model, usage={'prompt_tokens': 1, 'completion_tokens': 1}, finish_reason='stop',
                                   text=json.dumps({'args': task['canonical']}))

    monkeypatch.setattr(outside_rehearsal.tokenfactory, 'client', lambda: Client())
    output = tmp_path / 'outside-run.json'
    result = outside_rehearsal.execute(output)
    assert result['status'] == 'complete' and len(result['tools']) == 3
    assert len(calls) == 9 and all(row['passed'] == row['attempted'] == 3 for row in result['tools'])
    assert all(kwargs == {'seed': kwargs['seed'], 'temperature': 0, 'max_tokens': 256,
                          'chat_template_kwargs': {'enable_thinking': False}}
               for _, kwargs in calls)
    assert json.loads(output.read_text()) == result


def test_a_new_complete_run_archives_the_previous_result(tmp_path, monkeypatch, portable_tools):
    model = 'nvidia/test-nemotron'
    monkeypatch.setenv('TOKEN_FACTORY_MODEL', model)
    old = tmp_path / 'outside-run.json'
    old.write_text(json.dumps({'status': 'complete', 'finished_at': '2026-10-23T15:28:15+00:00'}))

    class Client:
        def chat(self, messages, **kwargs):
            task = next(task for task in outside_rehearsal.TASKS if task['task'] in messages[-1]['content'])
            return SimpleNamespace(model=model, usage={}, finish_reason='stop', text=json.dumps({'args': task['canonical']}))

    monkeypatch.setattr(outside_rehearsal.tokenfactory, 'client', lambda: Client())
    outside_rehearsal.execute(old)
    assert len(list((tmp_path / 'outside-runs').glob('*.json'))) == 1


def test_command_runner_needs_only_python_on_the_test_host(tmp_path):
    observed = outside_rehearsal.run([sys.executable, '-c', 'print("ready")'], tmp_path)
    assert observed == {'returncode': 0, 'output': 'ready\n'}
