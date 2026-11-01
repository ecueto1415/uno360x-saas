"""Transactional upstream POS checks; only the two isolated WSL lab tenants."""
from install_business_base import main

if __name__ == '__main__':
    main(modules=['uno360x_business_base','point_of_sale'], min_tests=10,
         log_name='pos-tests.log',
         test_tags='/uno360x_business_base,/point_of_sale:TestPoSStock,'
                   '/point_of_sale:TestPosSimpleOrders.test_01,'
                   '/point_of_sale:TestPosSimpleOrders.test_02')
