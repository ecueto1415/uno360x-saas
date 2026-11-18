/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("actions").add("uno360x_wait_credit", async (env, action) => {
    const params = action.params;
    const notification = env.services.notification;
    const close = notification.add("Procesando la nota de crédito electrónica…", {
        title: "UNO360X", type: "info", sticky: true,
    });
    const deadline = Date.now() + 180000;
    try {
        while (Date.now() < deadline) {
            const result = await env.services.orm.call(
                "account.move", "uno360x_credit_progress", [[params.original_id], params.issue_id]
            );
            if (result.done) {
                close();
                notification.add(result.message, { type: result.success ? "success" : "warning" });
                return env.services.action.doAction(result.action, { clearBreadcrumbs: true });
            }
            await new Promise((resolve) => setTimeout(resolve, 2000));
        }
        close();
        notification.add("La DGII sigue procesando la nota. Consulta su estado desde la factura.", { type: "warning" });
    } catch (error) {
        close();
        notification.add("No se pudo actualizar el estado. Consulta la nota desde la factura.", { type: "warning" });
    }
    return env.services.action.doAction(params.original_action, { clearBreadcrumbs: true });
});
