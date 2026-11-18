/** @odoo-module **/
import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useEffect } from "@odoo/owl";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        const orm = useService("orm");
        useEffect(() => {
            const root = this.model.root;
            if (root.resModel !== "account.move" || !root.resId ||
                !Object.hasOwn(root.data, "uno360x_fiscal_live_token")) {
                return;
            }
            const id = root.resId;
            let stopped = false;
            let timer;
            const check = async () => {
                let pending = true;
                try {
                    const result = await orm.call("account.move", "uno360x_fiscal_progress", [[id]]);
                    if (stopped || this.model.root.resId !== id) {
                        return;
                    }
                    pending = result.pending;
                    if (result.token !== this.model.root.data.uno360x_fiscal_live_token) {
                        if (this.model.root.isDirty) {
                            pending = true;
                        } else {
                            await this.model.load();
                        }
                    }
                } catch (error) {
                    pending = true;
                }
                if (!stopped && pending) {
                    timer = setTimeout(check, 2000);
                }
            };
            check();
            return () => {
                stopped = true;
                clearTimeout(timer);
            };
        }, () => [this.model.root.resId, this.model.root.data.uno360x_fiscal_live_token]);
    },
});
