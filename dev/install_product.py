"""Full portable product rehearsal, only fictional WSL tenants."""
from install_business_base import main

if __name__=='__main__':
    main(modules=['uno360x_business_base','uno360x_quote_ui','uno360x_ecf_core',
                  'uno360x_payroll_hr','uno360x_jenifer_core','uno360x_projects_services'],
         min_tests=18,log_name='product-tests.log')
