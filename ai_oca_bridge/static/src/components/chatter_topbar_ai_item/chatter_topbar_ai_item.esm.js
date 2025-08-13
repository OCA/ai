/** @odoo-module **/

import {Component, markup} from "@odoo/owl";
import {usePopover} from "@web/core/popover/popover_hook";

export class ChatterAIItemPopover extends Component {
    static template = "ai_oca_bridge.ChatterAIItemPopover";
}

export class ChatterAIItem extends Component {
    static template = "ai_oca_bridge.ChatterAIItem";
    static props = {bridge: Object};

    setup() {
        super.setup();
        this.popover = usePopover();
        this.tooltipPopover = null;
    }
    get tooltipInfo() {
        return {
            help: markup(this.props.bridge.description || ""),
        };
    }
    onMouseEnter(ev) {
        this.closeTooltip();
        this.tooltipPopover = this.popover.add(
            ev.currentTarget,
            ChatterAIItemPopover,
            this.tooltipInfo,
            {
                closeOnClickAway: true,
                position: "top",
            }
        );
    }

    onMouseLeave() {
        this.closeTooltip();
    }

    closeTooltip() {
        if (this.tooltipPopover) {
            this.tooltipPopover();
            this.tooltipPopover = null;
        }
    }
}
