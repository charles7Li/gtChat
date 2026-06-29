VALID_ROUTES = {"trend_report_path", "imitation_plan_path", "full_pipeline_path", "reference_video_imitation_path"}


def route_from_state(state: dict) -> str:
    route = state.get("route")
    if route in VALID_ROUTES:
        return route
    return "trend_report_path"
