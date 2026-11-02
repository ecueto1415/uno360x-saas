/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
// Keep native closePos synchronization and warnings; change its final destination.
patch(PosStore.prototype, {
    redirectToBackend() {
        window.location.href = "/uno360x-pos";
    },
});
