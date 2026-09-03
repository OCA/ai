import {registry} from "@web/core/registry";

registry.category("web_tour.tours").add("ai_systray_tour", {
    test: true,
    steps: () => [
        {
            content: "Wait for navbar to load and click AI Systray icon button",
            trigger: ".o_ai_systray button",
            run: "click",
        },
        {
            content: "Verify AI Systray dropdown menu opens",
            trigger: ".o_ai_systray_dropdown",
        },
        {
            content: "Click on the active thread item in dropdown",
            trigger: ".o_ai_systray_thread_list a:contains('Systray Tour Partner')",
            run: "click",
        },
        {
            content: "Verify navigation to the target partner record form view",
            trigger: ".o_breadcrumb:contains('Systray Tour Partner')",
        },
        {
            content: "Wait for chatter container to load",
            trigger: ".o-mail-Chatter",
        },
        {
            content: "Verify AI Assistant tab is active",
            trigger: ".o-mail-Chatter-tab-ai.active",
        },
    ],
});
