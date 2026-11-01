import itertools
import unittest
from control.catalog import installation_profile


class CatalogTests(unittest.TestCase):
    def test_all_eight_combinations_have_exact_modules(self):
        options={'payroll_hr':'uno360x_payroll_hr','jenifer_ai':'uno360x_jenifer_core',
                 'projects_services':'uno360x_projects_services'}
        for count in range(4):
            for chosen in itertools.combinations(options,count):
                with self.subTest(chosen=chosen):
                    plan=installation_profile(chosen)
                    self.assertEqual(set(plan['addons']),{'uno360x_business_base','uno360x_quote_ui','uno360x_ecf_core','uno360x_auth_bridge','uno360x_workspace'}|{options[x] for x in chosen})
                    self.assertFalse(plan['production_deployment'])

    def test_order_is_irrelevant_unknown_scope_rejected(self):
        self.assertEqual(installation_profile(['jenifer_ai','payroll_hr']),installation_profile(['payroll_hr','jenifer_ai']))
        with self.assertRaises(ValueError):installation_profile(['unknown'])

    def test_external_integrations_remain_gated(self):
        gates=installation_profile([])['gates']
        self.assertEqual(gates['fiscal_transmission'],'not_implemented_blocked')
        self.assertEqual(gates['jenifer_external_ai'],'provider_adapter_pending_disabled')
