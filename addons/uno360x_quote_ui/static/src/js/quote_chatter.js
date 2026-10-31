/** @odoo-module **/
import { onMounted } from "@odoo/owl";
import { Chatter } from "@mail/chatter/web_portal/chatter";
import { patch } from "@web/core/utils/patch";

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            const form = document.querySelector(".ux_quote_form");
            if (this.props.threadModel !== "sale.order" || !this.props.threadId || !form) return;
            Promise.resolve(this.toggleComposer("message")).then(() => {
                requestAnimationFrame(() => {
                    const content = form.querySelector(".o_content");
                    if (content) content.scrollTop = 0;
                });
            });
        });
    },
});
