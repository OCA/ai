import {onMounted, onWillUnmount} from "@odoo/owl";
import {router} from "@web/core/browser/router";
import {patch} from "@web/core/utils/patch";
import {WithSearch} from "@web/search/with_search/with_search";

/** Search models of the mounted views, the last one being the active view. */
const searchModels = [];

patch(WithSearch.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => searchModels.push(this.searchModel));
        onWillUnmount(() => {
            const index = searchModels.lastIndexOf(this.searchModel);
            if (index !== -1) {
                searchModels.splice(index, 1);
            }
        });
    },
});

function facetLabel(facet) {
    const values = facet.values.join(` ${facet.separator || "or"} `);
    return facet.title ? `${facet.title}: ${values}` : values;
}

/** The record of a form view, from the URL (it follows the pager). */
function formResId(controller, viewType) {
    if (viewType !== "form") {
        return undefined;
    }
    const resId = router.current.resId || controller.props?.resId;
    return typeof resId === "number" ? resId : undefined;
}

/**
 * The view the user is looking at, as context of a new AI agent conversation:
 * model, record of a form view, view type, domain, groupings and filters.
 *
 * @returns {{ resModel: string, resId?: number, viewContext: Object }|null}
 */
export function getCurrentViewContext(env) {
    const controller = env.services.action.currentController;
    const action = controller?.action;
    if (!action || action.type !== "ir.actions.act_window" || !action.res_model) {
        return null;
    }
    const resModel = action.res_model;
    const viewType = controller.view?.type ?? controller.props?.type;
    const viewContext = {
        action_name: controller.displayName || action.display_name || action.name,
        view_type: viewType,
    };
    const searchModel = searchModels.findLast((model) => model.resModel === resModel);
    if (searchModel && viewType !== "form") {
        viewContext.domain = searchModel.domain;
        viewContext.group_by = searchModel.groupBy;
        viewContext.facets = searchModel.facets.map(facetLabel);
    }
    return {resModel, resId: formResId(controller, viewType), viewContext};
}
