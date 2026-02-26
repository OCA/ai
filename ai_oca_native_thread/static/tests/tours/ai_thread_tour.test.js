import {registry} from "@web/core/registry";

registry.category("web_tour.tours").add("ai_thread_tour", {
    test: true,
    steps: () => [
        {
            content: "Wait for list view to load, then click the first record",
            trigger: ".o_list_table .o_data_row:first-child .o_data_cell",
            run: "click",
        },
        {
            content: "Wait for the chatter to be fully loaded",
            trigger: ".o-mail-Chatter",
        },
        {
            content: "Click on AI Thread button in the chatter",
            trigger: "button.o-mail-Chatter-tab-ai",
            run: "click",
        },
        {
            content: "Check that the AI chat interface appears and type a message",
            trigger: ".o_ai_thread_container textarea",
            run: "edit Hello AI",
        },
        {
            content: "Click send",
            trigger: ".o_ai_input_area button",
            run: "click",
        },
        {
            content: "Wait for the user message to appear",
            trigger: ".o_ai_messages:contains('Hello AI')",
        },
        {
            content:
                "Check that the dropdown is no longer on 'new', and has selected the generated thread",
            trigger: ".o_ai_thread_container select",
            run: () => {
                const select = document.querySelector(".o_ai_thread_container select");
                const options = Array.from(select.querySelectorAll("option")).map(
                    (o) => ({value: o.value, text: o.textContent, selected: o.selected})
                );
                if (select.value === "new" || select.value === "") {
                    throw new Error(
                        "Select value is wrong: '" +
                            select.value +
                            "'. HTML: " +
                            select.innerHTML +
                            " Options: " +
                            JSON.stringify(options)
                    );
                }
            },
        },
        {
            content: "Click on the next record pager button",
            trigger: ".o_pager button.o_pager_next:enabled",
            run: "click",
        },
        {
            content: "Wait for the second partner to load",
            trigger: ".o_breadcrumb:contains('Test Tour Partner 2')",
        },
        {
            content:
                "Ensure the AI tab is still active and the previous message is gone",
            trigger: ".o_ai_thread_container",
            run: () => {
                const messages = document.querySelector(".o_ai_messages");
                if (messages && messages.textContent.includes("Hello AI")) {
                    throw new Error(
                        "The AI thread should not contain messages from the previous record!"
                    );
                }
            },
        },
    ],
});
