from django import template

register = template.Library()


@register.inclusion_tag("rutas/pagination.html", takes_context=True)
def pagination(context, page, parameter="page", label="P?ginas", placement="bottom"):
    request = context["request"]
    query = request.GET.copy()

    def url(number):
        params = query.copy()
        params[parameter] = str(number)
        return "?" + params.urlencode()

    numbers = [{"number": number, "ellipsis": number == page.paginator.ELLIPSIS,
                "url": "" if number == page.paginator.ELLIPSIS else url(number)}
               for number in page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1)]
    return {"page": page, "numbers": numbers, "label": label, "placement": placement,
            "first_url": url(1), "last_url": url(page.paginator.num_pages),
            "previous_url": url(page.previous_page_number()) if page.has_previous() else "",
            "next_url": url(page.next_page_number()) if page.has_next() else "",
            "parameter": parameter,
            "jump_id": f"jump-{parameter}-{placement}",
            "filters": [(key, value) for key, values in query.lists() if key != parameter for value in values]}
