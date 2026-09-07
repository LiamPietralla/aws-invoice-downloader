import argparse
import csv
import datetime
import os

import boto3
import requests
from dateutil.relativedelta import relativedelta

OUTPUT_DIR = "./aws_invoices"
DEFAULT_CSV_PATH = "./aws_invoices_report.csv"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download AWS Invoices and export metadata with payment status."
    )
    parser.add_argument(
        "--csv",
        "-c",
        nargs="?",
        const=DEFAULT_CSV_PATH,
        metavar="CSV_FILE_PATH",
        help="Export invoice metadata and payment status to CSV.",
    )

    parser.add_argument(
        "--start-date",
        "-s",
        required=False,
        metavar="START_DATE",
        help="Start date for downloading invoices (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        "-e",
        required=False,
        metavar="END_DATE",
        help="End date for downloading invoices (YYYY-MM-DD).",
    )
    return parser.parse_args()


def create_invoicing_client():
    return boto3.client("invoicing", region_name="us-east-1")


def get_account_id():
    """Dynamically fetch the current AWS Account ID using STS."""
    sts = boto3.client("sts")
    return sts.get_caller_identity()["Account"]


def generate_monthly_windows(start_dt):
    now = datetime.datetime.now(datetime.UTC)
    current_start = start_dt

    while current_start < now:
        next_month = current_start + relativedelta(months=1)
        current_end = next_month - datetime.timedelta(seconds=1)

        current_end = min(current_end, now)

        yield current_start, current_end
        current_start = next_month


def list_all_invoices(client, account_id, start_dt):
    invoices = []
    paginator = client.get_paginator("list_invoice_summaries")

    for window_start, window_end in generate_monthly_windows(start_dt):
        start_str = window_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"Fetching invoices for window: {start_str[:10]} to {end_str[:10]}...")

        page_iterator = paginator.paginate(
            Selector={"ResourceType": "ACCOUNT_ID", "Value": account_id},
            Filter={
                "TimeInterval": {
                    "StartDate": start_str,
                    "EndDate": end_str,
                }
            },
        )

        for page in page_iterator:
            summaries = page.get("InvoiceSummaries", [])
            invoices.extend(summaries)

    return invoices


def export_to_csv(invoices, csv_path):
    fieldnames = [
        "InvoiceId",
        "AccountId",
        "InvoiceType",
        "IssuedDate",
        "DueDate",
        "InvoicingEntity",
        "BillingYear",
        "BillingMonth",
        "TotalAmount",
        "TotalBeforeTax",
        "SubTotal",
        "Discounts",
        "Taxes",
        "Fees",
        "CurrencyCode",
        "TaxAuthorityStatus",
    ]

    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)

    with open(csv_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for item in invoices:
            billing_period = item.get("BillingPeriod", {})
            entity = item.get("Entity", {})
            base_amt = item.get("BaseCurrencyAmount", {})
            amt_breakdown = base_amt.get("AmountBreakdown", {})

            row = {
                "InvoiceId": item.get("InvoiceId", ""),
                "AccountId": item.get("AccountId", ""),
                "InvoiceType": item.get("InvoiceType", ""),
                "IssuedDate": item.get("IssuedDate", ""),
                "DueDate": item.get("DueDate", ""),
                "InvoicingEntity": entity.get("InvoicingEntity", ""),
                "BillingYear": billing_period.get("Year", ""),
                "BillingMonth": billing_period.get("Month", ""),
                "TotalAmount": base_amt.get("TotalAmount", "0.00"),
                "TotalBeforeTax": base_amt.get("TotalAmountBeforeTax", "0.00"),
                "SubTotal": amt_breakdown.get("SubTotalAmount", "0.00"),
                "Discounts": amt_breakdown.get("Discounts", {}).get(
                    "TotalAmount", "0.00"
                ),
                "Taxes": amt_breakdown.get("Taxes", {}).get("TotalAmount", "0.00"),
                "Fees": amt_breakdown.get("Fees", {}).get("TotalAmount", "0.00"),
                "CurrencyCode": base_amt.get("CurrencyCode", "USD"),
                "TaxAuthorityStatus": item.get("TaxAuthorityStatus", "ISSUED"),
            }
            writer.writerow(row)

    print(f"\n Successfully exported CSV metadata report to: {csv_path}")


def download_invoice_pdf(client, invoice_id, output_directory):
    response = client.get_invoice_pdf(InvoiceId=invoice_id)
    doc_url = response["InvoicePDF"]["DocumentUrl"]

    pdf_response = requests.get(doc_url, timeout=30)
    pdf_response.raise_for_status()

    file_path = os.path.join(output_directory, f"invoice_{invoice_id}.pdf")
    with open(file_path, "wb") as f:
        f.write(pdf_response.content)

    print(f" Successfully downloaded: {file_path}")


def get_default_start_date():
    """Return a default start date of the start of the previous month."""
    today = datetime.datetime.now(tz=datetime.UTC).date()
    first_day_of_current_month = today.replace(day=1)
    last_day_of_previous_month = first_day_of_current_month - datetime.timedelta(days=1)
    return last_day_of_previous_month.replace(day=1)


def parse_date(date_str):
    """Parse a date string in the format YYYY-MM-DD and return a date object."""
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()


def main():
    args = parse_args()

    # Setup dates
    START_DATE = (
        parse_date(args.start_date) if args.start_date else get_default_start_date()
    )
    print(f"Using start date: {START_DATE}")
    START_DATE = datetime.datetime.combine(START_DATE, datetime.time.min).replace(
        tzinfo=datetime.UTC
    )

    END_DATE = (
        parse_date(args.end_date)
        if args.end_date
        else datetime.datetime.now(tz=datetime.UTC).date()
    )
    print(f"Using end date: {END_DATE}")
    END_DATE = datetime.datetime.combine(END_DATE, datetime.time.min).replace(
        tzinfo=datetime.UTC
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client = create_invoicing_client()
    account_id = get_account_id()

    print(f"Authenticated AWS Account ID: {account_id}")

    invoices = list_all_invoices(client, account_id, START_DATE)

    unique_invoices = list({inv["InvoiceId"]: inv for inv in invoices}.values())
    print(f"\nTotal unique invoices found: {len(unique_invoices)}\n")

    if args.csv is not None:
        export_to_csv(unique_invoices, args.csv)

    for idx, item in enumerate(unique_invoices, start=1):
        invoice_id = item["InvoiceId"]
        billing_period = item.get("BillingPeriod", {})
        year = billing_period.get("Year", "N/A")
        month = billing_period.get("Month", "N/A")

        print(
            f"[{idx}/{len(unique_invoices)}] Processing Invoice: {invoice_id} ({year}-{month})"
        )
        download_invoice_pdf(client, invoice_id, OUTPUT_DIR)


if __name__ == "__main__":
    main()
