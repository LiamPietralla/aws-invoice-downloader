# AWS Invoice Downloader

Download AWS invoices by date range.

## Setup

The script requires that you have Python installed and that you have configured your AWS credentials.

The easiest way to login is to just get temporary credentials using your Console login by running: 

```bash
aws login
```

## Usage

Clone or download this repository.

```bash
git clone https://github.com/yourusername/aws-invoice-downloader.git
cd aws-invoice-downloader
```

Run the script with the desired arguments. For example:

```bash
uv run download_aws_invoices.py --start-date 2024-01-01 --end-date 2024-01-31 --c
```

If no end date is provided, the script will download invoices up to the current date.
If no start date is provided, the script will download invoices from the previous month.

