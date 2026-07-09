# Task 3 Analysis: Multiple Stakeholder Dashboard Architecture

Date: 2026-06-15

## Scope

This document now focuses only on task 3 from the original request:

- Check whether the current architecture supports multiple dashboard views cleanly.

It also adds an implementation requirement for Codex during delivery:

- Codex should check all MNH program dashboards to ensure the column layouts, widths, heights, and overall visual structure are consistent and clean.

## Short Answer

The current architecture can support multiple stakeholder dashboards, but not cleanly enough yet.

The codebase already has:

- a top-level page system using Dash Pages
- a dashboard configuration source in `data/visualizations/validated_dashboard.json`
- reusable MNID/MNH rendering helpers
- role and scope data that can be used for access decisions

The main problem is that dashboard composition is still partly hardcoded in the MNID renderer, especially the tab structure and section assembly. That means adding three stakeholder dashboards directly on top of the current design would work, but it would become harder to maintain unless a configuration-driven dashboard layer is introduced first.

## What the Current Architecture Already Supports

### 1. Route and page support

The app already has a valid page/routing structure:

- [app.py](/home/ghost/projects/Mahis_Reports/app.py:1)
- [pages/home.py](/home/ghost/projects/Mahis_Reports/pages/home.py:45)

This means the application can host multiple dashboard experiences without needing a routing rewrite.

### 2. Config-based dashboard lookup

The dashboard menu is already loaded from:

- [data/visualizations/validated_dashboard.json](/home/ghost/projects/Mahis_Reports/data/visualizations/validated_dashboard.json:4485)

The home page already selects dashboard definitions and routes MNID dashboards into the dedicated renderer:

- [pages/home.py](/home/ghost/projects/Mahis_Reports/pages/home.py:268)

This is a strong foundation for stakeholder-specific dashboard configs.

### 3. Reusable rendering pieces

The codebase already contains reusable building blocks:

- layout helpers in [mnid/layout.py](/home/ghost/projects/Mahis_Reports/mnid/layout.py:1)
- executive view sections in [mnid/executive_views.py](/home/ghost/projects/Mahis_Reports/mnid/executive_views.py:672)
- chart helpers in [mnid/chart_helpers.py](/home/ghost/projects/Mahis_Reports/mnid/chart_helpers.py:1)
- coverage and heatmap builders in [mnid/coverage.py](/home/ghost/projects/Mahis_Reports/mnid/coverage.py:1) and [mnid/heatmap.py](/home/ghost/projects/Mahis_Reports/mnid/heatmap.py:1)

This reduces the amount of new code needed.

### 4. User scope and role metadata

The app already loads user metadata including `uuid`, `role`, and `user_level`:

- [pages/home.py](/home/ghost/projects/Mahis_Reports/pages/home.py:132)
- [config.example.py](/home/ghost/projects/Mahis_Reports/config.example.py:266)

That is enough to drive dashboard visibility in the near term.

## Where the Current Architecture Is Not Clean Yet

### 1. Dashboard composition is still hardcoded

The biggest issue is in the MNID renderer:

- [mnid/app.py](/home/ghost/projects/Mahis_Reports/mnid/app.py:2427)
- [mnid/app.py](/home/ghost/projects/Mahis_Reports/mnid/app.py:2504)

The current tab set is defined directly in Python:

- Country Profile
- Operational Readiness
- Maternal
- Newborn

This means the current system is not yet a true stakeholder-dashboard engine. It is still one dashboard renderer with fixed assumptions.

### 2. Indicators are only partially config-driven

Indicators exist in JSON config, but runtime indicator resolution is still mixed with Python logic:

- [data/visualizations/validated_dashboard.json](/home/ghost/projects/Mahis_Reports/data/visualizations/validated_dashboard.json:4485)
- [data/visualizations/validated_dashboard.json](/home/ghost/projects/Mahis_Reports/data/visualizations/validated_dashboard.json:5462)
- [mnid/indicators.py](/home/ghost/projects/Mahis_Reports/mnid/indicators.py:1)

That is acceptable for the current baseline, but it makes stakeholder-specific branching harder if each dashboard starts introducing unique indicator groups.

### 3. Shared filters and dashboard-specific controls are split

Shared filters exist at the page level:

- [pages/home.py](/home/ghost/projects/Mahis_Reports/pages/home.py:296)

But additional controls are embedded inside the MNID sections:

- [mnid/app.py](/home/ghost/projects/Mahis_Reports/mnid/app.py:1066)
- [mnid/app.py](/home/ghost/projects/Mahis_Reports/mnid/app.py:1913)

This is manageable now, but if three stakeholder dashboards are implemented independently, those controls can drift and duplicate.

### 4. Role handling exists, but dashboard mapping does not

The app already uses role/scope data for access and filtering:

- [helpers/navigation_callbacks.py](/home/ghost/projects/Mahis_Reports/helpers/navigation_callbacks.py:78)
- [pages/configurations.py](/home/ghost/projects/Mahis_Reports/pages/configurations.py:1395)
- [pages/home.py](/home/ghost/projects/Mahis_Reports/pages/home.py:187)

But there is no current `role -> dashboard` mapping layer. Without that layer, stakeholder dashboards would be wired through ad hoc conditions.

## Clean Architecture Verdict

### Can the current architecture support multiple dashboard views?

Yes.

### Can it support them cleanly in its current form?

Not fully.

### What makes it feasible anyway?

These existing pieces make the refactor practical:

- config-based dashboard selection already exists
- the home page already routes MNID dashboard definitions into a single renderer
- reusable layout/chart/helper modules already exist
- user scope and role metadata already exist

### What must change for it to become clean?

At minimum:

- move stakeholder dashboard identity into explicit dashboard configs
- extract hardcoded tab composition from `mnid/app.py`
- introduce a role-to-dashboard mapping service
- keep shared MNH components reusable instead of cloning pages

## Recommended Direction for Task 3

The safest conclusion for task 3 is:

1. The current architecture is feasible for multiple dashboard views.
2. It is not yet clean enough to implement them by direct duplication.
3. A configuration-driven dashboard layer should be introduced before or alongside stakeholder-specific views.

Recommended model:

- one reusable MNH dashboard engine
- multiple stakeholder configs
- role-based dashboard access
- optional dashboard selector for users with access to more than one stakeholder view

## Added Delivery Requirement

When Codex implements or refactors the MNH stakeholder dashboards, it should also perform a dashboard quality pass across all MNH program dashboards to ensure:

- columns render correctly
- widths are balanced
- heights are visually consistent
- cards and charts align properly
- layouts are clean on the current supported screen sizes
- no dashboard section looks broken, cramped, or uneven

This should be treated as part of the task, not as optional cleanup.

## Suggested Acceptance Criteria for Task 3

Task 3 should be considered properly addressed only if the proposed architecture:

- supports Beginnings, NEST360 + NEOTREE, and MoH SRS as distinct dashboard views
- avoids copying large dashboard files per stakeholder
- keeps shared MNH rendering logic reusable
- allows dashboard visibility to be determined from user role or stakeholder mapping
- leaves room for a selector when a user can access more than one dashboard
- includes a review pass across all MNH program dashboards for column layout, width, height, and visual cleanliness

## Git Process Requirement

Any implementation work for this architecture should be committed incrementally during the process rather than as one large final commit.
