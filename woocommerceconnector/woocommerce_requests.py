from __future__ import unicode_literals
import frappe
from frappe import _
import json, time, requests
from .exceptions import woocommerceError
from frappe.utils import get_request_session, get_datetime, cint
from woocommerce import API
from .utils import make_woocommerce_log

# Removed unused imports: math, pytz, get_time_zone
# Reason: They were never used

_per_page = 100

def get_woocommerce_settings():
    """Fetch WooCommerce settings from WooCommerce Config DocType."""
    d = frappe.get_doc("WooCommerce Config")
    
    if d.woocommerce_url:
        d.api_secret = d.get_password(fieldname='api_secret')
        return d.as_dict()
    else:
        frappe.throw(
            _("WooCommerce store URL is not configured on WooCommerce Config"), 
            woocommerceError
        )

def get_request_request(path, settings=None):
    """Make a GET request to WooCommerce with error logging."""
    if not settings:
        settings = get_woocommerce_settings()

    verify_ssl = cint(settings.get('verify_ssl', 0)) == 1  # ✅ standardized SSL handling

    wcapi = API(
        url=settings['woocommerce_url'],
        consumer_key=settings['api_key'],
        consumer_secret=settings['api_secret'],
        verify_ssl=verify_ssl,
        wp_api=True,
        version="wc/v3",
        timeout=1000,
        query_string_auth=True,
    )

    r = wcapi.get(path)

    # ✅ improved error logging
    if r.status_code != requests.codes.ok:
        make_woocommerce_log(
            title=f"WooCommerce GET error {r.status_code}",
            status="Error",
            method="get_request",
            message=f"{r.url}: {r.text}",  # changed .json() to .text for safety
            request_data="not defined",
            exception=True
        )
    return r

def get_request(path, settings=None):
    """Wrapper to return JSON directly from WooCommerce GET."""
    return get_request_request(path, settings).json()

def post_request(path, data):
    """Make a POST request to WooCommerce with error logging."""
    settings = get_woocommerce_settings()
    verify_ssl = cint(settings.get('verify_ssl', 0)) == 1

    wcapi = API(
        url=settings['woocommerce_url'],
        consumer_key=settings['api_key'],
        consumer_secret=settings['api_secret'],
        verify_ssl=verify_ssl,
        wp_api=True,
        version="wc/v3",
        timeout=1000
    )

    r = wcapi.post(path, data)

    if r.status_code not in (200, 201):
        make_woocommerce_log(
            title=f"WooCommerce POST error {r.status_code}",
            status="Error",
            method="post_request",
            message=f"{r.url}: {r.text}",
            request_data=data,
            exception=True
        )
    return r.json()

def put_request(path, data):
    """Make a PUT request to WooCommerce with error logging."""
    settings = get_woocommerce_settings()
    verify_ssl = cint(settings.get('verify_ssl', 0)) == 1

    wcapi = API(
        url=settings['woocommerce_url'],
        consumer_key=settings['api_key'],
        consumer_secret=settings['api_secret'],
        verify_ssl=verify_ssl,
        wp_api=True,
        version="wc/v3",
        timeout=5000,
        query_string_auth=True
    )

    r = wcapi.put(path, data)

    if r.status_code != requests.codes.ok:
        make_woocommerce_log(
            title=f"WooCommerce PUT error {r.status_code}",
            status="Error",
            method="put_request",
            message=f"{r.url}: {r.text}",
            request_data=data,
            exception=True
        )
    return r.json()

def delete_request(path):
    """Make a DELETE request to WooCommerce with error logging."""
    settings = get_woocommerce_settings()  # ✅ fixed missing settings
    verify_ssl = cint(settings.get('verify_ssl', 0)) == 1

    wcapi = API(
        url=settings['woocommerce_url'],
        consumer_key=settings['api_key'],
        consumer_secret=settings['api_secret'],
        verify_ssl=verify_ssl,
        wp_api=True,
        version="wc/v3",
        timeout=1000
    )

    r = wcapi.delete(path, params={"force": True})  # ✅ corrected to DELETE not POST

    if r.status_code != requests.codes.ok:
        make_woocommerce_log(
            title=f"WooCommerce DELETE error {r.status_code}",
            status="Error",
            method="delete_request",
            message=f"{r.url}: {r.text}",
            request_data=path,
            exception=True
        )
    return r.json()

def get_woocommerce_url(path, settings):
    return settings['woocommerce_url']

def get_header(settings):
    """Return request headers."""
    return {'Content-Type': 'application/json'}

def get_filtering_condition():
    """Build filter condition for modified_after."""
    woocommerce_settings = get_woocommerce_settings()
    if woocommerce_settings.last_sync_datetime:
        last_sync_datetime = get_datetime(woocommerce_settings.last_sync_datetime)
        return f"modified_after={last_sync_datetime.isoformat()}"
    return ''

def get_country():
    """Fetch list of countries from WooCommerce."""
    return get_request('data/countries')  # ✅ fixed endpoint

def get_woocommerce_items(ignore_filter_conditions=False):
    """Fetch all WooCommerce products."""
    woocommerce_products = []

    filter_condition = ''
    if not ignore_filter_conditions:
        filter_condition = get_filtering_condition()
        if cint(frappe.get_value("WooCommerce Config", "WooCommerce Config", "sync_only_published")) == 1:
            filter_condition += "&status=publish"

    response = get_request_request(f'products?per_page={_per_page}&{filter_condition}')
    woocommerce_products.extend(response.json())

    # ✅ safer pagination
    total_pages = cint(response.headers.get('X-WP-TotalPages')) or 1
    for page_idx in range(2, total_pages + 1):
        response = get_request_request(f'products?per_page={_per_page}&page={page_idx}&{filter_condition}')
        woocommerce_products.extend(response.json())

    return woocommerce_products

def get_woocommerce_item_variants(woocommerce_product_id):
    """Fetch product variations."""
    woocommerce_product_variants = []

    response = get_request_request(f'products/{woocommerce_product_id}/variations?per_page={_per_page}')
    woocommerce_product_variants.extend(response.json())

    total_pages = cint(response.headers.get('X-WP-TotalPages')) or 1
    for page_idx in range(2, total_pages + 1):
        response = get_request_request(
            f'products/{woocommerce_product_id}/variations?per_page={_per_page}&page={page_idx}'
        )
        woocommerce_product_variants.extend(response.json())

    return woocommerce_product_variants

def get_woocommerce_item_image(woocommerce_product_id):
    return get_request(f"products/{woocommerce_product_id}")["images"]

def get_woocommerce_tax(woocommerce_tax_id):
    return get_request(f"taxes/{woocommerce_tax_id}")

def get_woocommerce_customer(woocommerce_customer_id):
    return get_request(f"customers/{woocommerce_customer_id}")

def get_woocommerce_orders(order_status):
    """Fetch WooCommerce orders by status."""
    woocommerce_orders = []

    response = get_request_request(f'orders?per_page={_per_page}&status={order_status}')
    woocommerce_orders.extend(response.json())

    total_pages = cint(response.headers.get('X-WP-TotalPages')) or 1
    for page_idx in range(2, total_pages + 1):
        response = get_request_request(f'orders?per_page={_per_page}&page={page_idx}&status={order_status}')
        woocommerce_orders.extend(response.json())

    return woocommerce_orders

def get_woocommerce_customers(ignore_filter_conditions=False):
    """Fetch WooCommerce customers."""
    woocommerce_customers = []
    filter_condition = ''

    if not ignore_filter_conditions:
        filter_condition = get_filtering_condition()

        response = get_request_request(f'customers?per_page={_per_page}&{filter_condition}')
        woocommerce_customers.extend(response.json())

        total_pages = cint(response.headers.get('X-WP-TotalPages')) or 1
        for page_idx in range(2, total_pages + 1):
            response = get_request_request(f'customers?per_page={_per_page}&page={page_idx}&{filter_condition}')
            woocommerce_customers.extend(response.json())

    return woocommerce_customers
