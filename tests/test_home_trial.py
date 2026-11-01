from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from deployment.home_trial import add_trial,STYLE,BANNER

ROOT=Path(__file__).resolve().parents[1]

class HomepageTrialTests(unittest.TestCase):
    def test_only_the_approved_block_is_added_and_existing_navigation_is_preserved(self):
        for language in ('es_ES','en_US'):
            original=(ROOT/'website_snapshots'/f'uno360x.homepage_public.{language}.xml').read_text(encoding='utf-8')
            result=add_trial(original)
            self.assertEqual(result.replace(STYLE,'',1).replace(BANNER,'',1),original)
            root=ET.fromstring(result)
            trial=next(e for e in root.iter() if e.get('id')=='uno360x-home-trial')
            self.assertEqual(trial.find('a').get('href'),'/prueba-saas')
            self.assertIn('todavía no crea una cuenta real',result)
    def test_a_second_insertion_and_an_unknown_homepage_are_rejected(self):
        original=(ROOT/'website_snapshots/uno360x.homepage_public.es_ES.xml').read_text(encoding='utf-8')
        with self.assertRaises(AssertionError):add_trial(add_trial(original))
        with self.assertRaises(AssertionError):add_trial('<div/>')
