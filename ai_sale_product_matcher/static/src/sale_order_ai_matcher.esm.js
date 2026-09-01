/** @odoo-module **/

import {registry} from "@web/core/registry";

export const saleOrderAiMatcherService = {
    dependencies: ["bus_service", "notification"],
    start(env, {bus_service, notification}) {
        bus_service.subscribe("ai_sale_product_matcher.requirement_done", (payload) => {
            if (payload.state === "done") {
                notification.add(
                    "AI gereksinimleri çıkarıldı — sayfayı yenileyin veya wizard'da Refresh yapın.",
                    {type: "success"}
                );
            } else if (payload.state === "error") {
                notification.add(`AI extraction failed: ${payload.error || ""}`, {
                    type: "danger",
                });
            }
        });
        return {};
    },
};

registry.category("services").add("sale_order_ai_matcher", saleOrderAiMatcherService);
