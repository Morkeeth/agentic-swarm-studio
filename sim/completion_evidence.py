"""Bounded content guard, separate from a model's screen agreement.

Not a general semantic oracle. A quoted navigation label cannot demonstrate a
read result. Pricing reads additionally need an explicit price/free/sales answer.
"""
import re

from sim.task_contract import task_page

CONTENT_JS = """() => {
 const root=(document.querySelector('main,[role=main],article')||document.body).cloneNode(true);
 root.querySelectorAll('nav,header,footer,script,style,button,form,[role=navigation]').forEach(e=>e.remove());
 root.querySelectorAll('a').forEach(e=>e.remove());
 return root.textContent.replace(/\\s+/g,' ').trim();
}"""
# The page's own name for itself: its title and its h1/h2 headings, outside nav, header and footer.
LANDMARKS_JS = """() => [document.title, ...[...document.querySelectorAll('h1,h2')]
 .filter(e => !e.closest('nav,header,footer,[role=navigation]') && e.getClientRects().length)
 .map(e => e.innerText)].map(t => (t || '').replace(/\\s+/g, ' ').trim()).filter(Boolean)"""
PRICING_TASK = re.compile(r'\b(price|prices|pricing|cost|costs|subscription|tarif|prix|co[uû]t)\b', re.I)
PRICE_ANSWER = re.compile(r'(?:[$€£]\s*\d|\d[\d.,]*\s*(?:USD|EUR|GBP|dollars?|euros?)\b|\bfree\b|\bcontact\s+(?:our\s+)?sales\b|\bgratuit\b)', re.I)


def names_page(name, landmarks, content):
    """For 'Open the X page': the landmark that names X, or ''. A shell with no content never names anything."""
    want = re.sub(r'\s+', ' ', name or '').strip().casefold()
    if not want or len(re.sub(r'\s+', ' ', content or '').strip()) < 40: return ''
    pattern = re.compile(r'(?<!\w)' + re.escape(want) + r'(?!\w)')
    return next((t for t in landmarks or () if pattern.search(re.sub(r'\s+', ' ', t).casefold())), '')


def check(task, evidence, content, http_status=None, landmarks=None):
    if http_status is not None and not 200 <= http_status < 400:
        return False, 'The final page did not load successfully.'
    name = task_page(task)
    if name and landmarks is not None:
        # Opening a named page is done when the page names itself; there is no answer to quote.
        return (True, '') if names_page(name, landmarks, content) else (False, f'This page does not name itself "{name}" in its title or main heading.')
    quote = re.sub(r'\s+', ' ', evidence or '').strip('"\'“”.… ')
    text = re.sub(r'\s+', ' ', content or '')
    # Compare without whitespace: textContent joins a heading and its paragraph with no space, while a quote keeps the line break.
    if len(quote) < 12 or re.sub(r'\s', '', quote) not in re.sub(r'\s', '', text):
        return False, 'The quoted answer is absent from page content; navigation alone is insufficient.'
    pricing_only = PRICING_TASK.search(task or '') and not re.search(r'\bor\b.*\b(?:how|works|under the hood)\b', task or '', re.I)
    if pricing_only and not PRICE_ANSWER.search(quote):
        return False, 'The quoted content does not state a price, free access or a contact-sales answer.'
    return True, ''
