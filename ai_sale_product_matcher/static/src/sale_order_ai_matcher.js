/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export const saleOrderAiMatcherService = {
    dependencies: ["bus_service", "notification"],
    start(env, { bus_service, notification }) {
        bus_service.subscribe("ai_sale_product_matcher.requirement_done", (payload) => {
            if (payload.state === "done") {
                notification.add("AI requirements extracted — reloading.", { type: "success" });
                // Reload form if on sale.order
                const actionService = env.services.action;
                if (actionService && actionService.currentController) {
                    const controller = actionService.currentController;
                    if (controller && controller.props && controller.props.resModel === "sale.order") {
                        controller.model.load();
                    }
                }
            } else if (payload.state === "error") {
                notification.add(`AI extraction failed: ${payload.error || ""}`, { type: "danger" });
            }
        });
        return {};
    },
};

registry.category("services").add("sale_order_ai_matcher", saleOrderAiMatcherService);
