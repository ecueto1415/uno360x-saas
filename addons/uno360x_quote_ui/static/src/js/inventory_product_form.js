/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";

class InventoryProductController extends FormController {
    setup() {
        super.setup();
        this.inventoryNotification = useService("notification");
    }

    get className() {
        return { ...super.className, "uno-inventory-new": this.model.root.isNew };
    }

    async beforeExecuteActionButton(params) {
        if (params.special === "save") {
            const creating = this.model.root.isNew;
            const saved = await this.save({ closable: true });
            if (saved && creating) {
                this.inventoryNotification.add(_t("Producto guardado."), { type: "success" });
            } else if (saved) {
                const listPath = "/uno360x/area/inventory";
                const previous = document.referrer ? new URL(document.referrer) : null;
                const destination = previous?.origin === window.location.origin && previous.pathname === listPath
                    ? previous
                    : new URL(listPath, window.location.origin);
                destination.searchParams.set("product_saved", "1");
                window.location.replace(destination);
            }
            return false;
        }
        if (params.special === "cancel") {
            await this.discard();
            return false;
        }
        return super.beforeExecuteActionButton(params);
    }
}

registry.category("views").add("uno360x_inventory_product", {
    ...formView,
    Controller: InventoryProductController,
});
