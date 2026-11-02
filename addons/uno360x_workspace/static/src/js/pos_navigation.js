/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
// Keep native closePos synchronization and warnings; change its final destination.
patch(PosStore.prototype, {
    async uno360xReturn() {
        // Returning to the workspace is not a cash closing or a cancelled opening.
        // Use Odoo's pending-order synchronization and its existing warning dialog.
        const synchronized = await this.push_orders_with_closing_popup();
        if (synchronized) {
            window.location.href = "/uno360x-pos";
        }
    },
    redirectToBackend() {
        window.location.href = "/uno360x-pos";
    },
});

// Revalidate an authenticated page restored from browser history.
window.addEventListener('pageshow',function(event){if(event.persisted)window.location.reload();});
