import importlib.util
from pathlib import Path
from datetime import date
import unittest

path=Path(__file__).resolve().parents[1]/'addons/uno360x_dgii_606/engine.py'
spec=importlib.util.spec_from_file_location('uno606_engine',path)
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)


def sample(**changes):
    row=dict(source='Factura ficticia',move_id=1,supplier='132364805',expense='02',
        ncf='B0100000001',modified='',issued='2026-11-03',paid='',services=1000,goods=0,
        total=1000,vat=180,vat_withheld=0,proportional=0,cost_vat=0,advance=180,
        vat_perceived=0,isr_type='',isr_withheld=0,isr_perceived=0,isc=0,other=0,tip=0,
        payment_form='04',credit=False,reviewed=True,original_reported=False)
    row.update(changes);return row


class Test606(unittest.TestCase):
    def report(self,rows,period='202611'):
        return engine.build('132364805',period,rows,today=date(2026,11,19))
    def test_b_and_e_header_structure(self):
        r=self.report([sample(),sample(ncf='E310000000001',move_id=2)])
        self.assertFalse(r['errors']);text=engine.export_txt(r).decode()
        self.assertEqual(text.splitlines()[0],'606|132364805|202611|2')
        self.assertTrue(all(len(s.split('|'))==23 for s in text.splitlines()[1:]))
        self.assertIn('1000.00|0.00|1000.00|180.00',text)
    def test_credit_positive_txt_negative_summary(self):
        r=self.report([sample(ncf='E340000000001',modified='E310000000001',credit=True,payment_form='06',original_reported=True)])
        self.assertFalse(r['errors']);self.assertEqual(r['totals']['total'],'-1000.00')
        self.assertNotIn('-1000',engine.export_txt(r).decode())
    def test_later_retention(self):
        r=self.report([sample(issued='2026-10-03',paid='2026-11-04',vat_withheld=54,isr_type='02',isr_withheld=100,payment_form='02')])
        self.assertFalse(r['errors']);self.assertEqual(r['totals']['total'],'0.00')
        self.assertEqual(r['totals']['isr_withheld'],'100.00')
        self.assertEqual(r['rows'][0]['issued'],'20261003')
    def test_previous_month_without_retention_blocked(self):
        self.assertTrue(self.report([sample(issued='2026-10-03',paid='2026-11-04',payment_form='02')])['errors'])
    def test_duplicates_missing_data_block_export(self):
        r=self.report([sample(),sample(expense=False,reviewed=False)])
        self.assertTrue(r['errors'])
        self.assertTrue(any(e['field']=='NCF duplicado' for e in r['errors']))
        with self.assertRaises(ValueError):engine.export_txt(r)
    def test_retention_requires_date_and_type(self):
        r=self.report([sample(vat_withheld=54,isr_withheld=100)])
        self.assertTrue(any(e['field']=='Fecha pago' for e in r['errors']))
        self.assertTrue(any(e['field']=='Tipo retención ISR' for e in r['errors']))
    def test_bad_tax_and_period(self):
        for change in [dict(vat=None),dict(cost_vat=181),dict(total=900),dict(payment_form=None),dict(issued='2026-11-30'),dict(supplier='123456789')]:
            self.assertTrue(self.report([sample(**change)])['errors'],change)
        self.assertTrue(self.report([sample()],period='202613')['errors'])
    def test_minor_expense_own_id(self):
        r=self.report([sample(ncf='B1300000001')]);self.assertFalse(r['errors'])
        r=self.report([sample(ncf='B1300000001',supplier='130052433')]);self.assertTrue(r['errors'])
    def test_empty_informative_not_fake_txt(self):
        r=self.report([]);self.assertTrue(r['errors'])
    def test_note_requires_original_reported_evidence(self):
        r=self.report([sample(ncf='B0400000001',modified='B0100000001',credit=True,payment_form='06')])
        self.assertTrue(any(e['field']=='NCF original reportado' for e in r['errors']))


if __name__=='__main__':unittest.main()
