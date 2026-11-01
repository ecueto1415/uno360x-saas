import unittest
from deployment.preflight import inspect


class DeploymentPreparationTests(unittest.TestCase):
    def config(self):
        return dict(environment='isolated_pilot',server_address='8.8.8.8',server_provider='Proveedor ficticio',
                    monthly_budget_usd=50,central_origin='https://app.uno360x.com',tenant_domain='empresas.uno360x.com',
                    smtp_config_path='/private/saas-mail.json',external_backup_destination='Referencia de prueba')
    def test_configuration_never_grants_deployment_or_claims_external_verification(self):
        report=inspect(self.config(),{'public_release_allowed':True})
        self.assertTrue(report['configuration_complete'])
        self.assertFalse(report['deployment_allowed']);self.assertFalse(report['external_state_verified'])
    def test_production_address_and_current_site_are_rejected(self):
        config=self.config();config['server_address']='140.82.47.80'
        self.assertFalse(inspect(config,{})['configuration_complete'])
        for origin in ('https://uno360x.com','https://www.uno360x.com','http://app.uno360x.com','https://app.uno360x.com.evil.example'):
            config=self.config();config['central_origin']=origin
            self.assertFalse(inspect(config,{})['configuration_complete'])
    def test_missing_inputs_and_local_targets_are_reported_without_connection(self):
        config=self.config();config.update(server_address='127.0.0.1',monthly_budget_usd=None,smtp_config_path=None)
        report=inspect(config,{})
        self.assertFalse(report['configuration_complete']);self.assertEqual(len(report['issues']),3)
