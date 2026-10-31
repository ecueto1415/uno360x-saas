/** @odoo-module **/
import { Component, useEffect, useState, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

function taxLabel(name) {
    return /^\s*(?:18(?:[.,]0+)?%\s+ITBIS|ITBIS\s+18(?:[.,]0+)?%)(?:\s|$)/i.test(name || "") ? "ITBIS 18%" : name;
}
class QuoteTaxSelect extends Component {
    static props = { ...standardFieldProps, domain: { type: Function, optional: true } };
    static components = { Dropdown, DropdownItem };
    static template = xml`<div class="ux_quote_tax_select">
        <span t-if="props.readonly" class="ux_tax_trigger"><t t-esc="label"/><i class="fa fa-angle-down ms-2"/></span>
        <Dropdown t-else="">
            <button class="ux_tax_trigger" type="button" t-att-disabled="state.busy"><t t-esc="label"/><i class="fa fa-angle-down ms-2"/></button>
            <t t-set-slot="content">
                <DropdownItem t-foreach="state.taxes" t-as="tax" t-key="tax.id" onSelected="() => this.select(tax.id)">
                    <span t-esc="tax.label"/><i t-if="selected.includes(tax.id)" class="fa fa-check ms-3 text-success"/>
                </DropdownItem>
                <DropdownItem onSelected="() => this.select(false)"><span>Sin impuesto</span><i t-if="!selected.length" class="fa fa-check ms-3 text-success"/></DropdownItem>
            </t>
        </Dropdown>
    </div>`;
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ taxes: [], busy: false });
        useEffect(() => {
            if (!this.props.readonly) this.loadTaxes();
        }, () => [this.props.readonly]);
    }
    async loadTaxes() {
        try {
            const domain = this.props.domain ? this.props.domain() : [["type_tax_use", "=", "sale"]];
            const taxes = await this.orm.searchRead("account.tax", domain, ["display_name"], { limit: 100 });
            this.state.taxes = taxes.map(t => ({ id: t.id, label: taxLabel(t.display_name) }));
        } catch {
            this.notification.add("No se pudieron cargar los impuestos disponibles.", { type: "warning" });
        }
    }
    get list() { return this.props.record.data[this.props.name]; }
    get selected() { return this.list.records.map(r => r.resId); }
    get label() {
        return this.list.records.map(r => taxLabel(r.data.display_name)).join(" + ") || "Sin impuesto";
    }
    async select(id) {
        if (this.props.readonly || this.state.busy) return;
        this.state.busy = true;
        try {
            await this.list.addAndRemove({ add: id ? [id] : [], remove: this.selected.filter(v => v !== id) });
        } catch (error) {
            this.notification.add("No se pudo cambiar el impuesto. Revisa la partida antes de guardar.", { type: "danger" });
            throw error;
        } finally { this.state.busy = false; }
    }
}
registry.category("fields").add("ux_quote_tax_select", {
    component: QuoteTaxSelect,
    listViewWidth: [145, 160],
    supportedTypes: ["many2many"],
    relatedFields: () => [{ name: "display_name", type: "char" }],
    extractProps: (info, dynamicInfo) => ({ domain: dynamicInfo.domain }),
});

class QuoteVersionMenu extends Component {
    static props = { ...standardFieldProps };
    static components = { Dropdown, DropdownItem };
    static template = xml`<Dropdown>
        <button type="button" class="ux_quote_version_trigger"><t t-if="versions.length">Versión <t t-esc="number(versions[0])"/></t><t t-else="">Sin versiones</t><i class="fa fa-angle-down ms-2"/></button>
        <t t-set-slot="content">
            <DropdownItem t-foreach="versions" t-as="version" t-key="version.resId" onSelected="() => this.open(version)">V<t t-esc="number(version)"/> · Ver previo PDF</DropdownItem>
            <span t-if="!versions.length" class="dropdown-item-text text-muted">Guarda la primera copia PDF.</span>
        </t>
    </Dropdown>`;
    setup() { this.action = useService("action"); }
    get versions() { return [...this.props.record.data[this.props.name].records].sort((a,b)=>b.resId-a.resId); }
    number(v) { return (v.data.display_name || v.data.name || "").split(" - V").pop().replace(/\.pdf$/i, ""); }
    open(v) { return this.action.doAction({ type: "ir.actions.act_url", url: `/web/content/${v.resId}?download=false`, target: "new" }); }
}
registry.category("fields").add("ux_quote_version_menu", {
    component: QuoteVersionMenu,
    supportedTypes: ["many2many"],
    relatedFields: () => [{ name: "display_name", type: "char" }],
});
