/**
 * MNID sidebar scrollspy — pure DOM, zero Dash callbacks, zero background pings.
 *
 * Uses a scroll event listener on both document (capture) and window so it
 * works regardless of which element is the actual scroll container.
 *
 * The key rule: find the last section whose top edge has crossed the
 * activation line. There is always a result — we never fall back to Overview
 * unless the page is genuinely scrolled to the top.
 */
(function () {
    'use strict';

    var SECTION_IDS   = ['mnid-summary','mnid-coverage','mnid-trends','mnid-performance','mnid-heatmap','mnid-comparative'];
    var ACTIVATION_Y  = 140;   /* px from viewport top to count as "active" */
    var _lastActive   = null;
    var _attached     = false;

    /* ── pick the deepest section whose top has passed ACTIVATION_Y ────────── */
    function activeSection() {
        var best = null;
        var bestTop = -Infinity;

        for (var i = 0; i < SECTION_IDS.length; i++) {
            var el = document.getElementById(SECTION_IDS[i]);
            if (!el) continue;
            var top = el.getBoundingClientRect().top;
            if (top <= ACTIVATION_Y && top > bestTop) {
                bestTop = top;
                best    = SECTION_IDS[i];
            }
        }

        /* Nothing has scrolled past the line yet — use the topmost visible section */
        if (!best) {
            for (var j = 0; j < SECTION_IDS.length; j++) {
                if (document.getElementById(SECTION_IDS[j])) return SECTION_IDS[j];
            }
        }
        return best;
    }

    /* ── update nav button classes ─────────────────────────────────────────── */
    function setActive(id) {
        if (!id || id === _lastActive) return;
        _lastActive = id;
        document.querySelectorAll('.mnid-nav-btn').forEach(function (btn) {
            var href = btn.getAttribute('href') || '';
            btn.classList.toggle('active', href === '#' + id);
        });
    }

    function onScroll() { setActive(activeSection()); }

    /* ── attach / detach ───────────────────────────────────────────────────── */
    function attach() {
        var count = SECTION_IDS.filter(function (id) { return !!document.getElementById(id); }).length;
        if (!count || _attached) return;
        _attached = true;
        /* capture:true catches scroll events from any child scroll container */
        document.addEventListener('scroll', onScroll, { passive: true, capture: true });
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }

    function detach() {
        if (!_attached) return;
        _attached   = false;
        _lastActive = null;
        document.removeEventListener('scroll', onScroll, { capture: true });
        window.removeEventListener('scroll', onScroll);
    }

    /* ── nav click → update immediately without waiting for scroll ─────────── */
    document.addEventListener('click', function (e) {
        var btn = e.target && e.target.closest && e.target.closest('.mnid-nav-btn');
        if (!btn) return;
        var href = (btn.getAttribute('href') || '').replace('#', '');
        if (href) { _lastActive = null; setActive(href); }
    }, true);

    /* ── re-attach whenever Dash re-renders the dashboard ──────────────────── */
    new MutationObserver(function () {
        var has = SECTION_IDS.some(function (id) { return !!document.getElementById(id); });
        if (has) { _attached = false; attach(); }  /* force re-attach on re-render */
        else detach();
    }).observe(document.body, { childList: true, subtree: true });

    attach();
}());
