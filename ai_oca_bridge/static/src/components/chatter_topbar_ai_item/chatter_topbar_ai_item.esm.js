import {Component, markup} from "@odoo/owl";
import {usePopover} from "@web/core/popover/popover_hook";

export class ChatterAIItemPopover extends Component {
    static template = "ai_oca_bridge.ChatterAIItemPopover";
    static props = {
        help: String,
        close: Function,
    };
}

export class ChatterAIItem extends Component {
    static template = "ai_oca_bridge.ChatterAIItem";
    static props = {bridge: Object};

    setup() {
        super.setup();
        this.popover = usePopover(ChatterAIItemPopover);
    }
    get tooltipInfo() {
        return markup(this.props.bridge.description || "");
    }
    onMouseEnter(ev) {
        this.closeTooltip();
        const help = this.tooltipInfo;
        this.popover.open(ev.currentTarget, {help});
    }

    onMouseLeave() {
        this.closeTooltip();
    }

    closeTooltip() {
        this.popover.close();
    }
}
