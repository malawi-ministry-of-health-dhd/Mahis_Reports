document.addEventListener("DOMContentLoaded", function () {

    // Sort counts
    const countContainer = document.getElementById("counts-container");
    if (countContainer) {
        new Sortable(countContainer, {
            animation: 150,
            handle: ".count-item",
            ghostClass: "sortable-ghost",
        });
    }

    // Sort sections
    const sectionContainer = document.getElementById("sections-container");
    if (sectionContainer) {
        new Sortable(sectionContainer, {
            animation: 150,
            handle: ".section-item",
            ghostClass: "sortable-ghost",
        });
    }

    // Sort charts inside each section
    document.querySelectorAll("[id^='charts-container']").forEach(el => {
        new Sortable(el, {
            animation: 150,
            handle: ".chart-item",
            ghostClass: "sortable-ghost",
        });
    });

});