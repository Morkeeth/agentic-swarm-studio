"""Retained navigation-only false approval and successful siblings."""
import pytest
from sim import app_swarm

@pytest.mark.parametrize('task,quote,content,status,expected', [
    ('See what Lumen Notes costs', 'Pricing', 'Lumen Notes keeps your notes in one place.', 200, False),
    ('Find the subscription price', 'View prices', 'The calculator explains how our subscription works.', 200, False),
    ('See the price of Atlas', '$19 per month', '404 Pricing $19 per month. This page does not exist.', 404, False),
    ('See what Lumen Notes costs', 'Starter plan is $19 per month.', 'Starter plan is $19 per month.', 200, True),
    ('Find the subscription price', 'Our subscription is free for everyone.', 'Our subscription is free for everyone.', 200, True),
    ('Read the getting started guide', 'Start by opening a collection, then choose one note to read.', 'Start by opening a collection, then choose one note to read.', 200, True),
    # Live run 19 Oct: the judge quotes heading and text on separate lines; textContent joins them with no space.
    ('Read the getting started guide', 'Getting started\n\nKeep one collection per project. Read a note before changing it.',
     'Getting startedKeep one collection per project. Read a note before changing it. Tag a note so you can find it again later.', 200, True),
])
def test_content_guard(task, quote, content, status, expected):
    state = app_swarm.completion(task, True, [{'url': 'https://example.invalid/', 'action': 'look'}], evidence=quote, content=content, http_status=status)
    assert (state['state'] == 'job_completed') == expected


# NVIDIA-100, 22 Oct: 76 of 122 hackathon apps had a visitor standing on the page "Open the X page" asked for, 25 were
# confirmed. On a page you were asked to open there is no answer to quote, so the page naming itself is the evidence.
ABOUT = 'We are four students who built AirIQ to track the air quality in our city every hour.'
@pytest.mark.parametrize('task,quote,content,landmarks,expected', [
    ('Open the About page', 'About', ABOUT, ['AirIQ', 'About'], True),
    ('Open the About Us page', 'About Us', ABOUT, ['About Us - AirIQ'], True),
    ('Open the About page', 'About', ABOUT, None, False),                     # the old call: a heading is never evidence
    ('Open the About page', 'About', ABOUT, ['AirIQ', 'Contact us'], False),  # a different page
    ('Open the About page', 'About', 'About', ['About'], False),              # a shell with a heading and nothing else
    ('Open the Blog page', 'Blog', ABOUT, ['Blogger tips'], False),           # a word inside another word
    ('Read the About page', 'About', ABOUT, ['About'], False),                # a read task stays strict
    ('See what Lumen Notes costs', 'Pricing', ABOUT, ['Pricing'], False),     # so does a pricing task
])
def test_opening_a_named_page_is_done_when_the_page_names_itself_and_only_then(task, quote, content, landmarks, expected):
    state = app_swarm.completion(task, True, [{'url': 'https://example.invalid/about', 'action': 'look'}],
                                 evidence=quote, content=content, http_status=200, landmarks=landmarks)
    assert (state['state'] == 'job_completed') == expected


def test_a_page_that_did_not_load_never_names_itself():
    from sim import completion_evidence
    assert completion_evidence.check('Open the About page', 'About', ABOUT, 404, ['About'])[0] is False


def test_the_judge_is_told_how_an_opened_page_is_shown_and_a_read_task_is_not():
    opened = app_swarm.confirm_messages({'goal': 'Open the Forum page'}, 'Forum', [])[0]['content']
    read = app_swarm.confirm_messages({'goal': 'Read the Forum page'}, 'Forum', [])[0]['content']
    assert 'naming itself as "Forum"' in opened and 'naming itself' not in read
