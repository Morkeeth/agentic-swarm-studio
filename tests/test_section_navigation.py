"""Regression for the real visitor unable to use the landing Models section link."""
from playwright.sync_api import sync_playwright
from sim.app_swarm import COLLECT, section_observation

def test_section_links_are_actions_but_empty_and_missing_targets_are_not():
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page()
        page.route('http://owned.test/', lambda route: route.fulfill(content_type='text/html',body='<a href="#models">Models</a><a href="#missing">Missing</a><a href="#">Top</a><section id="models"><h2>Models</h2><p>Actual readable model content</p></section>'))
        page.goto('http://owned.test/')
        choices=page.evaluate(COLLECT,36)
        assert [x['text'] for x in choices]==['Models']
        page.locator('[data-visit-n="1"]').click()
        assert page.evaluate('location.hash')=='#models'
        browser.close()


def test_section_jump_changes_text_observation_with_the_screen():
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page()
        html='<p>'+('Long introduction. '*400)+'</p><a href="#models">Models</a><section id="models"><h2>Models</h2><p>The visitor uses Model A; the evidence check uses Model B.</p></section>'
        page.route('http://owned.test/',lambda route:route.fulfill(content_type='text/html',body=html))
        page.goto('http://owned.test/')
        assert section_observation(page,page.locator('body').inner_text(),0)==('',0)
        page.get_by_role('link',name='Models',exact=True).click()
        full=page.locator('body').inner_text()
        section,offset=section_observation(page,full,0)
        assert offset > 3600
        assert 'Model A' in full[offset:offset+3600]
        assert 'Long introduction' not in section
        assert 'Model B' in section
        browser.close()
