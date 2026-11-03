import {Component} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

const VIEW_TYPE_LABELS = {
    activity: _t("Activity"),
    calendar: _t("Calendar"),
    cohort: _t("Cohort"),
    form: _t("Form"),
    gantt: _t("Gantt"),
    graph: _t("Graph"),
    hierarchy: _t("Hierarchy"),
    kanban: _t("Kanban"),
    list: _t("List"),
    map: _t("Map"),
    pivot: _t("Pivot"),
};

/**
 * "Related to:" of the AI agent conversations with a context: the document,
 * or the view (with its filters and groupings) the conversation started from.
 */
export class AgentContextBar extends Component {
    static template = "ai_agent.AgentContextBar";
    static props = {
        resModel: String,
        resId: {optional: true},
        resName: {optional: true},
        viewContext: {optional: true},
    };

    setup() {
        this.action = useService("action");
    }

    get viewTypeLabel() {
        const viewType = this.props.viewContext?.view_type;
        return VIEW_TYPE_LABELS[viewType] ?? viewType;
    }

    get label() {
        if (this.props.resId) {
            return this.props.resName || this.props.resModel;
        }
        return (
            this.props.viewContext?.action_name ||
            this.props.resName ||
            this.props.resModel
        );
    }

    get details() {
        if (this.props.resId || !this.props.viewContext) {
            return "";
        }
        const {facets = [], group_by: groupBy = []} = this.props.viewContext;
        const details = [...facets];
        if (groupBy.length) {
            details.push(_t("Grouped by: %s", groupBy.join(", ")));
        }
        return details.join(" · ");
    }

    open() {
        if (this.props.resId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: this.props.resModel,
                res_id: this.props.resId,
                views: [[false, "form"]],
            });
            return;
        }
        const viewContext = this.props.viewContext || {};
        const viewType =
            viewContext.view_type && viewContext.view_type !== "form"
                ? viewContext.view_type
                : "list";
        this.action.doAction({
            type: "ir.actions.act_window",
            name: this.label,
            res_model: this.props.resModel,
            views: [[false, viewType]],
            domain: viewContext.domain || [],
            context: viewContext.group_by?.length
                ? {group_by: viewContext.group_by}
                : {},
        });
    }
}
