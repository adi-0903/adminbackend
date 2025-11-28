from __future__ import annotations

from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Prefetch, Sum, Avg, F, Min, Max, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse, HttpRequest
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
from datetime import datetime, timedelta, date
from django.utils import timezone
from decimal import Decimal
import json
from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from django.utils.decorators import method_decorator
from django.views.decorators.http import condition
from typing import Any, Dict, List, Optional, Union, Type, Tuple
from rest_framework.serializers import Serializer
from .models import Collection, Customer, MarketMilkPrice, DairyInformation, RawCollection
from .serializers import (
    CollectionListSerializer,
    CollectionDetailSerializer,
    CustomerSerializer,
    MarketMilkPriceSerializer,
    DairyInformationSerializer,
    RawCollectionListSerializer,
    RawCollectionDetailSerializer,
    RawCollectionMilkRateSerializer
)
from .filters import CollectionFilter, RawCollectionFilter
from wallet.models import Wallet
from user.models import UserInformation
from django.conf import settings
import os
from reportlab.pdfgen import canvas

class MyDocTemplate(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logo_path = os.path.join(settings.BASE_DIR, 'static', 'logo', 'logo.png')

    def handle_documentBegin(self):
        super().handle_documentBegin()
        self.canv.setAuthor("NetPy Technologies")

    def beforePage(self):
        # Calculate page dimensions
        page_width = self.width + self.leftMargin + self.rightMargin
        page_height = self.height + self.topMargin + self.bottomMargin

        # Add "Dudhiya" text and logo at the bottom of each page
        self.canv.saveState()

        # Calculate center position
        center_x = page_width / 2

        # Add "Dudhiya" text at the bottom left
        self.canv.setFont('Helvetica-Bold', 10)
        self.canv.setFillColorRGB(0.5, 0.5, 0.5)  # Medium gray color
        self.canv.drawString(self.leftMargin, self.bottomMargin - 20, "Dudhiya")

        # Add "Powered by" text - centered, bold, and larger
        self.canv.setFont('Helvetica-Bold', 10)
        self.canv.setFillColorRGB(0, 0, 0)  # Reset to black
        text = "Powered by"
        text_width = self.canv.stringWidth(text, 'Helvetica-Bold', 10)

        # Position text in center, accounting for logo width
        logo_width = 60  # Width of the logo
        total_width = text_width + 5 + logo_width  # 5 is spacing between text and logo
        start_x = center_x - (total_width / 2)

        self.canv.drawString(start_x, self.bottomMargin - 20, text)

        # Add logo - positioned right after the text
        logo = Image(self.logo_path, width=60, height=20)
        logo.drawOn(self.canv, start_x + text_width + 5, self.bottomMargin - 25)

        self.canv.restoreState()

class ProRataReportGenerator:
    def __init__(self, request):
        self.request = request
        self.report_start_date = None
        self.report_end_date = None
    
    def _format_dairy_header(self, dairy_name: str, dairy_address: str = "") -> str:
        """
        Format dairy name and address for report headers.
        Returns dairy name in bold at 16pt, followed by a comma and non-bold address at 14pt if available.
        Both are displayed on the same line.
        """
        if dairy_address:
            # Use ReportLab's tags for formatting:
            # - <b> for bold dairy name
            # - <font size=14> for smaller address font size
            return f"<b>{dairy_name}</b>, <font size=14>{dairy_address}</font>"
        return f"<b>{dairy_name}</b>"

    def _generate_purchase_report(self, collections: QuerySet, doc: SimpleDocTemplate, styles: dict) -> list:
        """Generate the purchase report section with pagination support"""
        elements = []

        dairy_info = DairyInformation.objects.filter(author=self.request.user, is_active=True).first()
        dairy_name = dairy_info.dairy_name if dairy_info else self.request.user.username
        dairy_address = dairy_info.dairy_address if dairy_info and dairy_info.dairy_address else ""

        # Add dairy name and address in a single line with comma separator
        dairy_header = self._format_dairy_header(dairy_name, dairy_address)
        elements.append(Paragraph(dairy_header, styles['DairyNameLeft']))

        elements.append(Spacer(1, 5))

        elements.append(Paragraph('PURCHASE REPORT', styles['ReportTitle']))

        start_date = self.report_start_date
        end_date = self.report_end_date

        # Create a table for date range with DD/MM/YYYY format in a single line
        date_data = [[
            Paragraph(f"DATE: FROM\u00A0 {start_date.strftime('%d/%m/%Y')}\u00A0\u00A0\u00A0\u00A0 TO\u00A0 {end_date.strftime('%d/%m/%Y')}", styles['DateRange'])
        ]]

        date_table = Table(date_data, colWidths=[doc.width])
        date_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ]))

        elements.append(date_table)
        elements.append(Spacer(1, 8))

        daily_data = []
        header = ['DATE', 'WEIGHT', 'FAT %', 'FAT KG.', 'SNF %', 'SNF KG.', 'Amount (Rs.)']

        # Initialize grand totals - removed solid weight related fields
        grand_totals = {
            'total_kg': 0,
            'total_fat_kg': 0,
            'total_snf_kg': 0,
            'total_amount': 0,
            'purchase_amount': 0,
            'count': 0,
            'fat_percentage_sum': 0,
            'snf_percentage_sum': 0
        }

        for date in collections.values('collection_date').distinct().order_by('collection_date'):
            date_collections = collections.filter(collection_date=date['collection_date'])
            daily_totals = date_collections.aggregate(
                total_kg=Sum('kg'),
                total_fat_kg=Sum('fat_kg'),
                total_snf_kg=Sum('snf_kg'),
                total_amount=Sum('amount'),
                avg_fat_percentage=Avg('fat_percentage'),
                avg_snf_percentage=Avg('snf_percentage')
            )

            purchase_amount = daily_totals['total_amount']

            # Update grand totals - removed solid weight
            grand_totals['total_kg'] += daily_totals['total_kg']
            grand_totals['total_fat_kg'] += daily_totals['total_fat_kg']
            grand_totals['total_snf_kg'] += daily_totals['total_snf_kg']
            grand_totals['purchase_amount'] += purchase_amount
            grand_totals['count'] += 1
            grand_totals['fat_percentage_sum'] += daily_totals['avg_fat_percentage']
            grand_totals['snf_percentage_sum'] += daily_totals['avg_snf_percentage']

            daily_data.append([
                date['collection_date'].strftime('%d/%m/%Y'),
                f"{daily_totals['total_kg']:.2f}",
                f"{daily_totals['avg_fat_percentage']:.2f}",
                f"{daily_totals['total_fat_kg']:.3f}",
                f"{daily_totals['avg_snf_percentage']:.2f}",
                f"{daily_totals['total_snf_kg']:.3f}",
                f"{purchase_amount:.2f}",
            ])

        rows_per_page = 25
        total_rows = len(daily_data)
        total_pages = (total_rows + rows_per_page - 1) // rows_per_page

        col_widths = [
            doc.width * 0.15,   # DATE
            doc.width * 0.15,   # WEIGHT
            doc.width * 0.10,   # FAT %
            doc.width * 0.15,   # FAT KG
            doc.width * 0.10,   # SNF %
            doc.width * 0.15,   # SNF KG
            doc.width * 0.20    # Amount (Rs.)
        ]

        # Process each page
        for page_num in range(total_pages):
            start_idx = page_num * rows_per_page
            end_idx = min((page_num + 1) * rows_per_page, total_rows)

            page_data = daily_data[start_idx:end_idx]

            if page_num == total_pages - 1:
                # Calculate averages for percentages
                avg_fat_percentage = grand_totals['fat_percentage_sum'] / grand_totals['count'] if grand_totals['count'] > 0 else 0
                avg_snf_percentage = grand_totals['snf_percentage_sum'] / grand_totals['count'] if grand_totals['count'] > 0 else 0
                
                page_data.append([
                    'TOTAL:',
                    f"{grand_totals['total_kg']:.2f}",
                    f"{avg_fat_percentage:.2f}",
                    f"{grand_totals['total_fat_kg']:.3f}",
                    f"{avg_snf_percentage:.2f}",
                    f"{grand_totals['total_snf_kg']:.3f}",
                    f"{grand_totals['purchase_amount']:.2f}",
                ])

            table = Table([header] + page_data, colWidths=col_widths)

            table_style = [
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Courier-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Courier'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Left align dates
                ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),  # Right align amount
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ]

            if page_num == total_pages - 1:
                table_style.extend([
                    ('FONTNAME', (0, -1), (-1, -1), 'Courier-Bold'),
                    ('FONTSIZE', (0, -1), (-1, -1), 10),
                    ('TOPPADDING', (0, -1), (-1, -1), 12),
                    ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
                    ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
                ])

            table.setStyle(TableStyle(table_style))
            elements.append(table)

            elements.append(Spacer(1, 10))
            elements.append(Paragraph(
                f'Page {page_num + 1} of {total_pages}',
                styles['PageNumber']
            ))

            if page_num < total_pages - 1:
                elements.append(PageBreak())

        return elements 

    def _generate_milk_purchase_summary(self, collections: QuerySet, doc: SimpleDocTemplate, styles: dict) -> list:
        """Generate the milk purchase summary section with pagination support"""
        elements = []

        dairy_info = DairyInformation.objects.filter(author=self.request.user, is_active=True).first()
        dairy_name = dairy_info.dairy_name if dairy_info else self.request.user.username
        dairy_address = dairy_info.dairy_address if dairy_info and dairy_info.dairy_address else ""

        # Add dairy name and address in a single line with comma separator
        dairy_header = self._format_dairy_header(dairy_name, dairy_address)
        elements.append(Paragraph(dairy_header, styles['DairyNameLeft']))

        elements.append(Spacer(1, 5))

        elements.append(Paragraph('MILK PURCHASE SUMMARY', styles['ReportTitle']))

        start_date = self.report_start_date
        end_date = self.report_end_date

        # Get user's name from UserInformation model
        user_info = UserInformation.objects.filter(user=self.request.user).first()
        owner_name = user_info.name if user_info and user_info.name else self.request.user.username

        # Create a table for date range in a single line
        date_data = [[
            Paragraph(f"DATE: FROM\u00A0 {start_date.strftime('%d/%m/%Y')}\u00A0\u00A0\u00A0\u00A0 TO\u00A0 {end_date.strftime('%d/%m/%Y')}", styles['DateRange'])
        ], [
            Paragraph(f"Route & Name: {owner_name},[   ]", styles['DateRange'])
        ]]

        date_table = Table(date_data, colWidths=[doc.width])
        date_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ]))

        elements.append(date_table)
        elements.append(Spacer(1, 8))

        customer_data = []
        header = ['PARTY NAME', 'WEIGHT(KG)', 'FAT KG.', 'SNF KG.', 'PUR.VALUE', 'TOT.AMT']

        # Initialize grand totals - removed total_solid_weight
        grand_totals = {
            'total_weight': 0,
            'total_fat_kg': 0,
            'total_snf_kg': 0,
            'purchase_amount': 0,
            'total_amount': 0,
            'customer_count': 0
        }

        customers = Customer.objects.filter(collection__in=collections).distinct()

        for customer in customers:
            customer_collections = collections.filter(customer=customer)
            customer_totals = customer_collections.aggregate(
                total_weight=Sum('kg'),
                total_fat_kg=Sum('fat_kg'),
                total_snf_kg=Sum('snf_kg'),
                total_amount=Sum('amount')
            )

            purchase_amount = customer_totals['total_amount']
            final_amount = int(purchase_amount * Decimal('0.999'))

            # Update grand totals - removed solid weight
            grand_totals['total_weight'] += customer_totals['total_weight']
            grand_totals['total_fat_kg'] += customer_totals['total_fat_kg']
            grand_totals['total_snf_kg'] += customer_totals['total_snf_kg']
            grand_totals['purchase_amount'] += purchase_amount
            grand_totals['total_amount'] += final_amount
            grand_totals['customer_count'] += 1

            customer_data.append([
                f"{customer.customer_id}-{customer.name}",
                f"{customer_totals['total_weight']:.2f}",
                f"{customer_totals['total_fat_kg']:.3f}",
                f"{customer_totals['total_snf_kg']:.3f}",
                f"{purchase_amount:.2f}",
                f"{final_amount:.2f}"
            ])

        # Optimize rows per page for better space utilization
        rows_per_page = 25
        total_rows = len(customer_data)
        total_pages = (total_rows + rows_per_page - 1) // rows_per_page

        col_widths = [
            doc.width * 0.28,  # PARTY NAME - wider for names
            doc.width * 0.12,  # WEIGHT
            doc.width * 0.15,  # FAT KG
            doc.width * 0.15,  # SNF KG
            doc.width * 0.15,  # PUR.VALUE
            doc.width * 0.15   # TOT.AMT
        ]

        # Process each page
        for page_num in range(total_pages):
            if page_num > 0:
                elements.append(PageBreak())
                dairy_header = self._format_dairy_header(dairy_name, dairy_address)
                elements.append(Paragraph(dairy_header, styles['DairyNameLeft']))
                elements.append(Spacer(1, 5))
                elements.append(Paragraph('MILK PURCHASE SUMMARY (CONTINUED)', styles['ReportTitle']))

                # Add date range and Route & Name for continuation pages
                continuation_date_data = [[
                    Paragraph(f"DATE: FROM\u00A0 {start_date.strftime('%d/%m/%Y')}\u00A0\u00A0\u00A0\u00A0 TO\u00A0 {end_date.strftime('%d/%m/%Y')}", styles['DateRange'])
                ], [
                    Paragraph(f"Route & Name: {owner_name}, [   ]", styles['DateRange'])
                ]]

                continuation_date_table = Table(continuation_date_data, colWidths=[doc.width])
                continuation_date_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ]))

                elements.append(continuation_date_table)
                elements.append(Spacer(1, 8))

            start_idx = page_num * rows_per_page
            end_idx = min((page_num + 1) * rows_per_page, total_rows)

            page_data = customer_data[start_idx:end_idx]

            # Only add the totals row on the last page that has actual data
            if page_num == total_pages - 1:
                page_data.append([
                    f"TOTAL : {grand_totals['customer_count']} Customers",
                    f"{grand_totals['total_weight']:.2f}",
                    f"{grand_totals['total_fat_kg']:.3f}",
                    f"{grand_totals['total_snf_kg']:.3f}",
                    f"{grand_totals['purchase_amount']:.2f}",
                    f"{grand_totals['total_amount']:.2f}"
                ])

            table = Table([header] + page_data, colWidths=col_widths, repeatRows=1)

            table_style = [
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Courier-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Courier'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Left align party names
                ('ALIGN', (1, 1), (3, -1), 'CENTER'),  # Center align WEIGHT, FAT KG, and SNF KG
                ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),  # Right align PUR.VALUE and TOT.AMT
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ]

            if page_num == total_pages - 1:
                table_style.extend([
                    ('FONTNAME', (0, -1), (-1, -1), 'Courier-Bold'),
                    ('FONTSIZE', (0, -1), (-1, -1), 10),
                    ('TOPPADDING', (0, -1), (-1, -1), 12),
                    ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
                    ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
                ])

            table.setStyle(TableStyle(table_style))
            elements.append(table)

            # Add final total amount after the main table on the last page
            if page_num == total_pages - 1:
                elements.append(Spacer(1, 20))  # Increased spacing from 10 to 20 points

                # Check if AmountDetail style exists
                if 'AmountDetail' not in styles:
                    styles.add(ParagraphStyle(
                        name='AmountDetail',
                        parent=styles['Normal'],
                        fontSize=11,
                        fontName='Courier-Bold',
                        alignment=2,  # Right alignment
                        rightIndent=0,  # Remove right indent to align with table edge
                        spaceAfter=2
                    ))

                # Show only total amount without bank charges calculation
                total_amount = grand_totals['total_amount']
                
                # Just display the total amount as a paragraph, right-aligned
                total_amount_para = Paragraph(f"Total Amount: Rs. {total_amount:.2f}", styles['AmountDetail'])
                elements.append(total_amount_para)

            elements.append(Spacer(1, 5))
            elements.append(Paragraph(
                f'Page {page_num + 1} of {total_pages}',
                styles['PageNumber']
            ))

            # No PageBreak after the last page
            # This fixes the empty page issue

        return elements

    def _generate_customer_milk_bill(self, collections: QuerySet, doc: SimpleDocTemplate, styles: dict) -> list:
        """Generate the customer milk bill section"""
        elements = []

        # Get dairy information
        dairy_info = DairyInformation.objects.filter(author=self.request.user, is_active=True).first()
        dairy_name = dairy_info.dairy_name if dairy_info else self.request.user.username
        dairy_address = dairy_info.dairy_address if dairy_info and dairy_info.dairy_address else ""

        # Add dairy name (left-aligned, no underline)
        if 'DairyNameLeft' not in styles:
            styles.add(ParagraphStyle(
                name='DairyNameLeft',
                parent=styles['Heading1'],
                fontSize=16,  # This is the base font size for the dairy name
                spaceAfter=5,
                alignment=0,  # Left alignment
                fontName='Courier',  # Use regular Courier for base font
                allowWidows=0,
                allowOrphans=0,
                bulletFontName='Courier-Bold',  # For bold parts
                htmlSlash=1  # Enable HTML parsing
            ))

        # Add dairy name and address in a single line with comma separator
        dairy_header = self._format_dairy_header(dairy_name, dairy_address)
        elements.append(Paragraph(dairy_header, styles['DairyNameLeft']))

        elements.append(Spacer(1, 5))

        # Add centered MILK BILL title
        elements.append(Paragraph('MILK BILL', styles['ReportTitle']))

        start_date = self.report_start_date
        end_date = self.report_end_date
        customer = collections.first().customer

        # Add DateRangeRight style if not exists
        if 'DateRangeRight' not in styles:
            styles.add(ParagraphStyle(
                name='DateRangeRight',
                parent=styles['Normal'],
                fontSize=10,  # Slightly smaller font
                spaceAfter=8,
                alignment=2,  # Right alignment
                fontName='Courier',
                wordWrap='CJK',  # Prevent normal word wrapping
                allowWidows=0,
                allowOrphans=0
            ))

        # Get user's name from UserInformation model
        user_info = UserInformation.objects.filter(user=self.request.user).first()
        owner_name = user_info.name if user_info and user_info.name else self.request.user.username

        # Create a table for party details and date
        party_data = [
            [
                Paragraph(f"Party Name: {customer.customer_id}-{customer.name}", styles['PartyName']),
                Paragraph("", styles['DateRangeRight'])  # Empty cell for alignment
            ],
            [
                Paragraph(f"Route & Name: {owner_name}, [   ]", styles['CustomerPhone']),
                Paragraph(f"DATE: FROM {start_date.strftime('%d/%m/%Y')} TO {end_date.strftime('%d/%m/%Y')}", styles['DateRangeRight'])
            ]
        ]

        # Create table for party details with specific column widths
        party_table = Table(party_data, colWidths=[doc.width*0.45, doc.width*0.55])
        party_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),  # Right align date
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('RIGHTPADDING', (1, 0), (1, -1), 20),  # Add right padding to the date column
        ]))

        elements.append(party_table)
        elements.append(Spacer(1, 8))

        data = []
        # Modified column headers - removed FAT RT, SNF RT, MILK RT
        header = ['DATE', 'WEIGHT', 'FAT %', 'CLR', 'SNF %', 'FAT KG', 'SNF KG', 'B Rate', 'Rate', 'AMOUNT']
        data.append(header)

        # Initialize totals
        totals = {
            'total_kg': 0,
            'total_fat_kg': 0,
            'total_snf_kg': 0,
            'total_amount': 0,
            'fat_percentage_sum': 0,
            'snf_percentage_sum': 0,
            'count': 0
        }

        for collection in collections.order_by('collection_date', 'collection_time'):
            # Add AM/PM based on collection_time
            time_suffix = "AM" if collection.collection_time == "morning" else "PM"
            # Modified row data - removed fat_rate, snf_rate, milk_rate
            rate = (collection.amount)/(collection.kg)
            row = [
                f"{collection.collection_date.strftime('%d/%m/%Y')} {time_suffix}",
                f"{collection.kg:.2f}",
                f"{collection.fat_percentage:.2f}",
                f"{collection.clr:.2f}" if collection.clr else "-",
                f"{collection.snf_percentage:.2f}",
                f"{collection.fat_kg:.3f}",
                f"{collection.snf_kg:.3f}",
                f"{collection.milk_rate:.2f}",
                f"{rate:.2f}",
                f"{collection.amount:.2f}"
            ]
            data.append(row)

            # Update totals
            totals['total_kg'] += collection.kg
            totals['total_fat_kg'] += collection.fat_kg
            totals['total_snf_kg'] += collection.snf_kg
            totals['total_amount'] += collection.amount
            totals['fat_percentage_sum'] += collection.fat_percentage
            totals['snf_percentage_sum'] += collection.snf_percentage
            totals['count'] += 1

        # Add totals row
        avg_fat = totals['fat_percentage_sum'] / totals['count'] if totals['count'] > 0 else 0
        avg_snf = totals['snf_percentage_sum'] / totals['count'] if totals['count'] > 0 else 0
        totals_row = [
            'TOTAL',
            f"{totals['total_kg']:.2f}",
            f"{avg_fat:.2f}",
            "-",  # CLR total not needed
            f"{avg_snf:.2f}",
            f"{totals['total_fat_kg']:.3f}",
            f"{totals['total_snf_kg']:.3f}",
            "",  # Empty B Rate column for totals row
            "",  # Empty Rate column for totals row
            f"{totals['total_amount']:.2f}"
        ]
        data.append(totals_row)

        # Create table with specific column widths - adjusted for removed columns
        col_widths = [
            doc.width * 0.15,   # DATE - Increased width for date with AM/PM
            doc.width * 0.09,   # WEIGHT
            doc.width * 0.09,   # FAT %
            doc.width * 0.09,   # CLR
            doc.width * 0.09,   # SNF %
            doc.width * 0.09,   # FAT KG
            doc.width * 0.09,   # SNF KG
            doc.width * 0.09,   # B Rate (new column)
            doc.width * 0.09,   # Rate (new column)
            doc.width * 0.13    # AMOUNT
        ]

        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Courier-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Courier'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Left align dates
            ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),  # Right align amount
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ]))

        elements.append(table)

        # Add amount calculations
        total_amount = totals['total_amount']
        bank_charges = total_amount * Decimal('0.001')  # 0.1% charges (1 - 0.999)
        net_amount = int(total_amount - bank_charges)

        # Create styles for amount details if not exists
        if 'AmountDetail' not in styles:
            styles.add(ParagraphStyle(
                name='AmountDetail',
                parent=styles['Normal'],
                fontSize=11,
                fontName='Courier-Bold',
                alignment=2,  # Right alignment
                rightIndent=0,  # Remove right indent to align with table edge
                spaceAfter=2
            ))

        # Add spacer before amount details
        elements.append(Spacer(1, 20))  # Increased spacing from 10 to 20 points

        # Create a table for the final calculations - removed solid weight
        final_data = [
            ['Total Amount', 'Rs.', f"{total_amount:.2f}"],
            ['Less: Bank Charges', 'Rs.', f"{bank_charges:.2f}"],
            ['Net Amount', 'Rs.', f"{net_amount:.2f}"]
        ]

        # Create table with three columns for perfect alignment
        col_widths = [doc.width*0.82, doc.width*0.06, doc.width*0.12]
        final_table = Table(final_data, colWidths=col_widths)
        
        # Add underlines for the bank charges and net amount rows
        final_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),  # Right align labels
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),  # Center align Rs.
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),  # Right align amounts
            ('FONTNAME', (0, 0), (2, -1), 'Courier-Bold'),  # Set font
            ('FONTSIZE', (0, 0), (2, -1), 11),  # Set font size
            ('LINEABOVE', (2, 0), (2, 0), 1, colors.black),  # Line above Total Amount - only above amount
            ('LINEBELOW', (2, 1), (2, 1), 1, colors.black, 2),  # Line after bank charges only under amount
            ('LINEBELOW', (2, 2), (2, 2), 1, colors.black, 2),  # Line after net amount only under amount
            ('RIGHTPADDING', (2, 0), (2, -1), 3),  # Match the data table padding
            ('LEFTPADDING', (0, 0), (0, -1), 3),   # Match the data table padding
            ('TOPPADDING', (0, 0), (2, -1), 4),    # Reduced top padding from 8 to 4
            ('BOTTOMPADDING', (0, 0), (2, -1), 4), # Reduced bottom padding from 8 to 4
        ]))

        elements.append(final_table)

        return elements 

    def generate_purchase_report(self, request: HttpRequest) -> Response:
        """Generate only the purchase report PDF for the given date range"""
        # Get date range from query parameters
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not all([start_date_str, end_date_str]):
            return Response(
                {'error': 'start_date and end_date are required query parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Parse date in DD-MM-YYYY format
            start_date = datetime.strptime(start_date_str, '%d-%m-%Y').date()
            end_date = datetime.strptime(end_date_str, '%d-%m-%Y').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use DD-MM-YYYY'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get collections for the date range - filter for is_pro_rata=True
        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date,
            is_pro_rata=True
        ).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No pro-rata collections found for the specified date range'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Set report dates as instance attributes
        self.report_start_date = start_date
        self.report_end_date = end_date

        # Create PDF with custom template
        buffer = BytesIO()
        doc = MyDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=20,
            leftMargin=20,
            topMargin=30,
            bottomMargin=50
        )

        # Get styles and define common styles
        styles = getSampleStyleSheet()

        # Add required custom styles
        styles.add(ParagraphStyle(
            name='DairyNameLeft',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=5,
            alignment=0,  # Left alignment
            fontName='Courier',  # Use regular Courier for base font
            allowWidows=0,
            allowOrphans=0,
            bulletFontName='Courier-Bold',  # For bold parts
            htmlSlash=1  # Enable HTML parsing
        ))

        styles.add(ParagraphStyle(
            name='DairyAddress',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,  # Left alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=10,
            alignment=1,  # Center alignment
            fontName='Courier-Bold'
        ))

        styles.add(ParagraphStyle(
            name='DateRange',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,  # Left alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='DateRangeRight',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=2,  # Right alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='PageNumber',
            parent=styles['Normal'],
            fontSize=9,
            alignment=1,  # Center alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='AmountDetail',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=2,  # Right alignment
            rightIndent=0,  # Remove right indent to align with table edge
            spaceAfter=2
        ))

        styles.add(ParagraphStyle(
            name='SolidWeight',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=0,  # Left alignment
            leftIndent=0,  # Remove left indent to fully left align
            spaceAfter=2
        ))

        # Generate elements
        elements = []

        # Add title and date range with DD-MM-YYYY format
        title = Paragraph(f"Milk Purchase Report ({start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')})", styles['ReportTitle'])
        elements.append(title)

        # Add purchase report
        elements.extend(self._generate_purchase_report(collections, doc, styles))

        # Build PDF
        doc.build(elements)

        # Prepare response
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="milk_purchase_report_{start_date.strftime("%d-%m-%Y")}_to_{end_date.strftime("%d-%m-%Y")}.pdf"'

        return response

    def generate_purchase_summary_report(self, request: HttpRequest) -> Response:
        """Generate only the purchase summary report PDF for the given date range"""
        # Get date range from query parameters
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not all([start_date_str, end_date_str]):
            return Response(
                {'error': 'start_date and end_date are required query parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Parse date in DD-MM-YYYY format
            start_date = datetime.strptime(start_date_str, '%d-%m-%Y').date()
            end_date = datetime.strptime(end_date_str, '%d-%m-%Y').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use DD-MM-YYYY'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Set report dates as instance attributes
        self.report_start_date = start_date
        self.report_end_date = end_date

        # Get collections for the date range - filter for is_pro_rata=True
        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date,
            is_pro_rata=True
        ).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No pro-rata collections found for the specified date range'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Create PDF with custom template
        buffer = BytesIO()
        doc = MyDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=20,
            leftMargin=20,
            topMargin=30,
            bottomMargin=50
        )

        # Get styles and define common styles
        styles = getSampleStyleSheet()

        # Add required custom styles
        styles.add(ParagraphStyle(
            name='DairyNameLeft',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=5,
            alignment=0,  # Left alignment
            fontName='Courier',  # Use regular Courier for base font
            allowWidows=0,
            allowOrphans=0,
            bulletFontName='Courier-Bold',  # For bold parts
            htmlSlash=1  # Enable HTML parsing
        ))

        styles.add(ParagraphStyle(
            name='DairyAddress',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,  # Left alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=10,
            alignment=1,  # Center alignment
            fontName='Courier-Bold'
        ))

        styles.add(ParagraphStyle(
            name='DateRange',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,  # Left alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='DateRangeRight',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=2,  # Right alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='PageNumber',
            parent=styles['Normal'],
            fontSize=9,
            alignment=1,  # Center alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='AmountDetail',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=2,  # Right alignment
            rightIndent=0,  # Remove right indent to align with table edge
            spaceAfter=2
        ))

        styles.add(ParagraphStyle(
            name='SolidWeight',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=0,  # Left alignment
            leftIndent=0,  # Remove left indent to fully left align
            spaceAfter=2
        ))

        # Generate elements
        elements = []

        # Add title and date range with DD-MM-YYYY format
        title = Paragraph(f"Milk Purchase Summary Report ({start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')})", styles['ReportTitle'])
        elements.append(title)

        # Add milk purchase summary
        elements.extend(self._generate_milk_purchase_summary(collections, doc, styles))

        # Build PDF
        doc.build(elements)

        # Prepare response
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="milk_purchase_summary_{start_date.strftime("%d-%m-%Y")}_to_{end_date.strftime("%d-%m-%Y")}.pdf"'

        return response 

    def generate_full_report(self, request: HttpRequest) -> Response:
        """Generate a complete milk purchase report PDF including purchase report, summary and customer bills"""
        # Get date range from query parameters
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not all([start_date_str, end_date_str]):
            return Response(
                {'error': 'start_date and end_date are required query parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Parse date in DD-MM-YYYY format
            start_date = datetime.strptime(start_date_str, '%d-%m-%Y').date()
            end_date = datetime.strptime(end_date_str, '%d-%m-%Y').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use DD-MM-YYYY'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get collections for the date range - filter for is_pro_rata=True
        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date,
            is_pro_rata=True
        ).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No pro-rata collections found for the specified date range'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Set report dates as instance attributes
        self.report_start_date = start_date
        self.report_end_date = end_date

        # Create PDF with custom template
        buffer = BytesIO()
        doc = MyDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=20,
            leftMargin=20,
            topMargin=30,
            bottomMargin=50
        )

        # Get styles and define common styles
        styles = getSampleStyleSheet()

        # Add required custom styles
        styles.add(ParagraphStyle(
            name='DairyNameLeft',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=5,
            alignment=0,  # Left alignment
            fontName='Courier',  # Use regular Courier for base font
            allowWidows=0,
            allowOrphans=0,
            bulletFontName='Courier-Bold',  # For bold parts
            htmlSlash=1  # Enable HTML parsing
        ))

        styles.add(ParagraphStyle(
            name='DairyAddress',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,  # Left alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=10,
            alignment=1,  # Center alignment
            fontName='Courier-Bold'
        ))

        styles.add(ParagraphStyle(
            name='DateRange',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,  # Left alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='DateRangeRight',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=2,  # Right alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='PageNumber',
            parent=styles['Normal'],
            fontSize=9,
            alignment=1,  # Center alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='AmountDetail',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=2,  # Right alignment
            rightIndent=0,  # Remove right indent to align with table edge
            spaceAfter=2
        ))

        styles.add(ParagraphStyle(
            name='SolidWeight',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=0,  # Left alignment
            leftIndent=0,  # Remove left indent to fully left align
            spaceAfter=2
        ))

        # Add PartyName style
        styles.add(ParagraphStyle(
            name='PartyName',
            parent=styles['Normal'],
            fontSize=12,
            fontName='Courier-Bold',
            spaceAfter=2,
            alignment=0  # Left alignment
        ))

        # Add CustomerPhone style
        styles.add(ParagraphStyle(
            name='CustomerPhone',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=2,
            alignment=0  # Left alignment
        ))

        # Generate all elements
        elements = []

        # Add title and date range with DD-MM-YYYY format
        title = Paragraph(f"Milk Collection Report ({start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')})", styles['ReportTitle'])
        elements.append(title)

        # Add purchase report
        elements.extend(self._generate_purchase_report(collections, doc, styles))

        # Add PageBreak before milk purchase summary
        elements.append(PageBreak())

        # Add milk purchase summary directly (without needing additional PageBreak)
        milk_purchase_elements = self._generate_milk_purchase_summary(collections, doc, styles)
        elements.extend(milk_purchase_elements)

        # We don't need to add a PageBreak here as we've fixed the pagination in _generate_milk_purchase_summary

        # Add individual customer milk bills (start on new page)
        elements.append(PageBreak())

        customers = Customer.objects.filter(collection__in=collections).distinct()
        for customer in customers:
            customer_collections = collections.filter(customer=customer)
            if customer_collections.exists():
                elements.extend(self._generate_customer_milk_bill(
                    customer_collections, doc, styles
                ))
                if customer != customers.last():
                    elements.append(PageBreak())

        # Build PDF
        doc.build(elements)

        # Prepare response
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="milk_full_report_{start_date.strftime("%d-%m-%Y")}_to_{end_date.strftime("%d-%m-%Y")}.pdf"'

        return response

    def generate_full_customer_report(self, request: HttpRequest) -> Response:
        """Generate a PDF report with milk bills for all customers for the given date range"""
        # Get date range from query parameters
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not all([start_date_str, end_date_str]):
            return Response(
                {'error': 'start_date and end_date are required query parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Parse date in DD-MM-YYYY format
            start_date = datetime.strptime(start_date_str, '%d-%m-%Y').date()
            end_date = datetime.strptime(end_date_str, '%d-%m-%Y').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use DD-MM-YYYY'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get collections for the date range - filter for is_pro_rata=True
        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date,
            is_pro_rata=True
        ).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No pro-rata collections found for the specified date range'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Set report dates as instance attributes
        self.report_start_date = start_date
        self.report_end_date = end_date

        # Create PDF with custom template
        buffer = BytesIO()
        doc = MyDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=20,
            leftMargin=20,
            topMargin=30,
            bottomMargin=50
        )

        # Get styles and define common styles
        styles = getSampleStyleSheet()

        # Add required custom styles
        styles.add(ParagraphStyle(
            name='DairyNameLeft',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=5,
            alignment=0,  # Left alignment
            fontName='Courier',  # Use regular Courier for base font
            allowWidows=0,
            allowOrphans=0,
            bulletFontName='Courier-Bold',  # For bold parts
            htmlSlash=1  # Enable HTML parsing
        ))

        styles.add(ParagraphStyle(
            name='DairyAddress',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,  # Left alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=10,
            alignment=1,  # Center alignment
            fontName='Courier-Bold'
        ))

        styles.add(ParagraphStyle(
            name='DateRange',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,  # Left alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='DateRangeRight',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=2,  # Right alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='PageNumber',
            parent=styles['Normal'],
            fontSize=9,
            alignment=1,  # Center alignment
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='AmountDetail',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=2,  # Right alignment
            rightIndent=0,  # Remove right indent to align with table edge
            spaceAfter=2
        ))

        styles.add(ParagraphStyle(
            name='SolidWeight',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=0,  # Left alignment
            leftIndent=0,  # Remove left indent to fully left align
            spaceAfter=2
        ))

        # Add PartyName style
        styles.add(ParagraphStyle(
            name='PartyName',
            parent=styles['Normal'],
            fontSize=12,
            fontName='Courier-Bold',
            spaceAfter=2,
            alignment=0  # Left alignment
        ))

        # Add CustomerPhone style
        styles.add(ParagraphStyle(
            name='CustomerPhone',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=2,
            alignment=0,  # Left alignment
            fontName='Courier'
        ))

        # Generate all elements
        elements = []

        # Add title and date range with DD-MM-YYYY format
        title = Paragraph(f"Customer Milk Bills ({start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')})", styles['ReportTitle'])
        elements.append(title)
        elements.append(Spacer(1, 10))

        # Add individual customer milk bills
        customers = Customer.objects.filter(collection__in=collections).distinct()
        for i, customer in enumerate(customers):
            customer_collections = collections.filter(customer=customer)
            if customer_collections.exists():
                if i > 0:  # Add page break before each customer except the first
                    elements.append(PageBreak())
                elements.extend(self._generate_customer_milk_bill(
                    customer_collections, doc, styles
                ))

        # Build PDF
        doc.build(elements)

        # Prepare response
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="customer_milk_bills_{start_date.strftime("%d-%m-%Y")}_to_{end_date.strftime("%d-%m-%Y")}.pdf"'

        return response

    def generate_customer_report(self, request: HttpRequest) -> Response:
        """Generate report PDF for specific customers in the given date range"""
        # Get parameters from query parameters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        customer_ids = request.query_params.get('customer_ids')

        if not all([start_date, end_date, customer_ids]):
            return Response(
                {'error': 'start_date, end_date, and customer_ids are required query parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Parse date in DD-MM-YYYY format
            start_date = datetime.strptime(start_date, '%d-%m-%Y').date()
            end_date = datetime.strptime(end_date, '%d-%m-%Y').date()
            customer_ids = [int(id.strip()) for id in customer_ids.split(',')]
        except ValueError:
            return Response(
                {'error': 'Invalid date format (use DD-MM-YYYY) or invalid customer IDs'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Set report dates as instance attributes
        self.report_start_date = start_date
        self.report_end_date = end_date

        # Get collections for the customers in date range - filter for is_pro_rata=True
        collections = Collection.objects.filter(
            author=request.user,
            customer_id__in=customer_ids,
            collection_date__gte=start_date,
            collection_date__lte=end_date,
            is_pro_rata=True
        ).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No pro-rata collections found for the specified customers and date range'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Create PDF with custom template
        buffer = BytesIO()
        doc = MyDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=20,
            leftMargin=20,
            topMargin=30,
            bottomMargin=50
        )

        # Get styles
        styles = getSampleStyleSheet()

        # Add required custom styles
        styles.add(ParagraphStyle(
            name='DairyNameLeft',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=5,
            alignment=0,
            fontName='Courier',  # Use regular Courier for base font
            allowWidows=0,
            allowOrphans=0,
            bulletFontName='Courier-Bold',  # For bold parts
            htmlSlash=1  # Enable HTML parsing
        ))

        styles.add(ParagraphStyle(
            name='DairyAddress',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=10,
            alignment=1,
            fontName='Courier-Bold'
        ))

        styles.add(ParagraphStyle(
            name='DateRange',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=0,
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='DateRangeRight',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            alignment=2,
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='PageNumber',
            parent=styles['Normal'],
            fontSize=9,
            alignment=1,
            fontName='Courier'
        ))

        styles.add(ParagraphStyle(
            name='AmountDetail',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=2,
            rightIndent=0,  # Remove right indent to align with table edge
            spaceAfter=2
        ))

        styles.add(ParagraphStyle(
            name='SolidWeight',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Courier-Bold',
            alignment=0,  # Left alignment
            leftIndent=0,  # Remove left indent to fully left align
            spaceAfter=2
        ))

        # Add PartyName style
        styles.add(ParagraphStyle(
            name='PartyName',
            parent=styles['Normal'],
            fontSize=12,
            fontName='Courier-Bold',
            spaceAfter=2,
            alignment=0  # Left alignment
        ))

        styles.add(ParagraphStyle(
            name='CustomerPhone',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=2,
            alignment=0,
            fontName='Courier'
        ))

        # Generate elements
        elements = []

        # Generate reports for each customer
        customers = Customer.objects.filter(id__in=customer_ids)
        for customer in customers:
            customer_collections = collections.filter(customer=customer)
            if customer_collections.exists():
                elements.extend(self._generate_customer_milk_bill(
                    customer_collections, doc, styles
                ))
                if customer != customers.last():
                    elements.append(PageBreak())

        # Build PDF
        doc.build(elements)

        # Prepare response
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="customer_report_{start_date.strftime("%d-%m-%Y")}_to_{end_date.strftime("%d-%m-%Y")}.pdf"'

        return response

    def purchase_summary_report(self, request: HttpRequest) -> Response:
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not all([start_date, end_date]):
            return Response(
                {'error': 'start_date and end_date are required query parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date = datetime.strptime(start_date, '%d-%m-%Y').date()
            end_date = datetime.strptime(end_date, '%d-%m-%Y').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use DD-MM-YYYY'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Filter for is_pro_rata=True
        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date,
            is_pro_rata=True
        ).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No pro-rata collections found for the specified date range'},
                status=status.HTTP_404_NOT_FOUND
            )

        summary_data = []
        grand_totals = {
            'total_weight': 0,
            'total_fat_kg': 0,
            'total_snf_kg': 0,
            'purchase_amount': 0,
            'total_amount': 0,
            'total_solid_weight': 0,
            'customer_count': 0
        }

        customers = Customer.objects.filter(collection__in=collections).distinct()

        for customer in customers:
            customer_collections = collections.filter(customer=customer)
            customer_totals = customer_collections.aggregate(
                total_weight=Sum('kg'),
                total_fat_kg=Sum('fat_kg'),
                total_snf_kg=Sum('snf_kg'),
                total_amount=Sum('amount'),
                total_solid_weight=Sum('solid_weight')
            )

            purchase_amount = customer_totals['total_amount']
            final_amount = int(purchase_amount * Decimal('0.999'))

            grand_totals['total_weight'] += customer_totals['total_weight']
            grand_totals['total_fat_kg'] += customer_totals['total_fat_kg']
            grand_totals['total_snf_kg'] += customer_totals['total_snf_kg']
            grand_totals['purchase_amount'] += purchase_amount
            grand_totals['total_amount'] += final_amount
            grand_totals['customer_count'] += 1

            summary_data.append({
                'party_name': f"{customer.customer_id}-{customer.name}",
                'phone': customer.phone or '-',
                'weight': f"{customer_totals['total_weight']:.2f}",
                'fat_kg': f"{customer_totals['total_fat_kg']:.3f}",
                'snf_kg': f"{customer_totals['total_snf_kg']:.3f}",
                'purchase_value': f"{purchase_amount:.2f}",
                'total_amount': f"{final_amount:.2f}"
            })

        return Response({
            'summary_data': summary_data,
            'grand_totals': grand_totals
        })

class ProRataReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'], url_path='purchase-report-pdf')
    def purchase_report_pdf(self, request: HttpRequest) -> Response:
        """API endpoint to generate the purchase report PDF for pro-rata collections."""
        generator = ProRataReportGenerator(request)
        return generator.generate_purchase_report(request)
    
    @action(detail=False, methods=['get'], url_path='generate_purchase_report')
    def generate_purchase_report(self, request: HttpRequest) -> Response:
        """Compatibility alias that returns the pro-rata purchase report PDF.
        This mirrors the non-pro-rata endpoint name so existing frontend code
        that calls `/collector/pro-rata-reports/generate_purchase_report/`
        will receive a valid PDF response instead of JSON.
        """
        generator = ProRataReportGenerator(request)
        return generator.generate_purchase_report(request)
    
    @action(detail=False, methods=['get'], url_path='purchase-report')
    def purchase_report(self, request: HttpRequest) -> Response:
        """API endpoint to get JSON purchase report data for pro-rata collections (grouped by date)."""
        # Compatibility: allow forcing PDF from this endpoint when requested via query params
        # so that links that accidentally hit this JSON route can still download a valid PDF.
        if request.query_params.get('format') == 'pdf' or request.query_params.get('download') in {'1', 'true', 'pdf'}:
            generator = ProRataReportGenerator(request)
            return generator.generate_purchase_report(request)
        from .models import Collection
        from django.db.models import Sum, Avg
        from rest_framework.pagination import PageNumberPagination
        
        collections = Collection.objects.filter(
            author=request.user,
            is_pro_rata=True
        ).values('collection_date').annotate(
            total_weight=Sum('kg'),
            total_fat_percentage=Avg('fat_percentage'),
            total_snf_percentage=Avg('snf_percentage'),
            total_fat_kg=Sum('fat_kg'),
            total_snf_kg=Sum('snf_kg'),
            total_amount=Sum('amount')
        ).order_by('collection_date')

        paginator = PageNumberPagination()
        paginator.page_size = 50
        paginator.page_size_query_param = 'page_size'
        paginator.max_page_size = 1000
        
        page = paginator.paginate_queryset(collections, request)
        if page is not None:
            return paginator.get_paginated_response(page)

        return Response(collections)
    
    @action(detail=False, methods=['get'], url_path='purchase-summary-report')
    def purchase_summary_report(self, request: HttpRequest) -> Response:
        """API endpoint to generate the purchase summary report PDF for pro-rata collections."""
        generator = ProRataReportGenerator(request)
        return generator.generate_purchase_summary_report(request)
    
    @action(detail=False, methods=['get'], url_path='full-report')
    def full_report(self, request: HttpRequest) -> Response:
        """API endpoint to generate the complete milk purchase report PDF for pro-rata collections."""
        generator = ProRataReportGenerator(request)
        return generator.generate_full_report(request)
    
    @action(detail=False, methods=['get'], url_path='customer-bills')
    def customer_bills(self, request: HttpRequest) -> Response:
        """API endpoint to generate milk bills for all customers with pro-rata collections."""
        generator = ProRataReportGenerator(request)
        return generator.generate_full_customer_report(request)
    
    @action(detail=False, methods=['get'], url_path='customer-report')
    def customer_report(self, request: HttpRequest) -> Response:
        """API endpoint to generate report for specific customers with pro-rata collections."""
        generator = ProRataReportGenerator(request)
        return generator.generate_customer_report(request)
    
    @action(detail=False, methods=['get'], url_path='purchase-summary-data')
    def purchase_summary_data(self, request: HttpRequest) -> Response:
        """API endpoint to get JSON data for the purchase summary report of pro-rata collections."""
        generator = ProRataReportGenerator(request)
        return generator.purchase_summary_report(request) 