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
from .models import Collection, Customer, MarketMilkPrice, DairyInformation, RawCollection, ProRataRateChart
from .serializers import (
    CollectionListSerializer,
    CollectionDetailSerializer,
    CustomerSerializer,
    MarketMilkPriceSerializer,
    DairyInformationSerializer,
    RawCollectionListSerializer,
    RawCollectionDetailSerializer,
    RawCollectionMilkRateSerializer,
    ProRataRateChartSerializer
)
from .filters import CollectionFilter, RawCollectionFilter
from wallet.models import Wallet
from user.models import UserInformation
from django.conf import settings
import os
from reportlab.pdfgen import canvas

class StandardResultsSetPagination(PageNumberPagination):
    page_size: int = 50
    page_size_query_param: str = 'page_size'
    max_page_size: int = 1000

class BaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    queryset: QuerySet
    serializer_class: Type[Serializer]

    def get_queryset(self) -> QuerySet:
        return self.queryset.filter(author=self.request.user, is_active=True)

    @transaction.atomic
    def perform_destroy(self, instance: Any) -> None:
        instance.soft_delete()

    def destroy(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(
                {
                    'message': f'{instance.__class__.__name__} deleted successfully',
                    'id': instance.id
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': f'Failed to delete {instance.__class__.__name__}.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, (ValidationError, DRFValidationError)):
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

class MarketMilkPriceViewSet(BaseViewSet):
    queryset = MarketMilkPrice.objects.all()
    serializer_class = MarketMilkPriceSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['price']
    ordering_fields = ['price', 'created_at']
    ordering = ['-created_at']

    def list(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        # Get only the most recent active milk price
        milk_price = MarketMilkPrice.objects.filter(
            author=request.user,
            is_active=True
        ).order_by('-created_at').first()

        if milk_price:
            serializer = self.get_serializer(milk_price)
            return Response(serializer.data)
        return Response(
            None,
            status=status.HTTP_200_OK
        )

    def create(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        try:
            # Soft delete any existing active milk price
            existing_price = MarketMilkPrice.objects.filter(
                author=request.user,
                is_active=True
            ).first()

            if existing_price:
                existing_price.soft_delete()

            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to create milk price. Please check your input.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to update milk price. Please check your input.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

class DairyInformationViewSet(BaseViewSet):
    queryset = DairyInformation.objects.all()
    serializer_class = DairyInformationSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['dairy_name']
    ordering_fields = ['dairy_name', 'rate_type', 'created_at']
    ordering = ['-created_at']

    def list(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        # Get only the most recent active dairy information
        dairy_info = DairyInformation.objects.filter(
            author=request.user,
            is_active=True
        ).order_by('-created_at').first()

        if dairy_info:
            serializer = self.get_serializer(dairy_info)
            return Response(serializer.data)
        return Response(
            
            None,
            status=status.HTTP_200_OK
        )

    def create(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        try:
            # Soft delete any existing active dairy information
            existing_dairy = DairyInformation.objects.filter(
                author=request.user,
                is_active=True
            ).first()

            if existing_dairy:
                existing_dairy.soft_delete()

            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to create dairy information. Please check your input.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to update dairy information. Please check your input.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

class ProRataRateChartViewSet(BaseViewSet):
    queryset = ProRataRateChart.objects.all()
    serializer_class = ProRataRateChartSerializer
    
    def list(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        # Get only the most recent active chart
        chart = ProRataRateChart.objects.filter(
            author=request.user,
            is_active=True
        ).order_by('-created_at').first()

        if chart:
            serializer = self.get_serializer(chart)
            return Response(serializer.data)
        
        # If no chart exists, return empty or 404? 
        # Returning 404 is consistent with other singleton views here
        return Response(
            {
                'detail': 'No pro rata rate chart found.'
            },
            status=status.HTTP_404_NOT_FOUND
        )

    def create(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        try:
            # Soft delete any existing active chart
            existing_chart = ProRataRateChart.objects.filter(
                author=request.user,
                is_active=True
            ).first()

            if existing_chart:
                existing_chart.soft_delete()

            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to create pro rata rate chart. Please check your input.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

class CustomerViewSet(BaseViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'phone']

    def get_queryset(self) -> QuerySet:
        """
        Override the default get_queryset to handle search separately.
        """
        # Start with the base query for active customers belonging to the current user
        queryset = self.queryset.filter(author=self.request.user, is_active=True)

        # Only apply the search filter if a search parameter is explicitly provided
        search_term = self.request.query_params.get('search', None)
        if search_term:
            # Create Q objects for each search field
            queries = [
                Q(**{f"{field}__icontains": search_term})
                for field in self.search_fields
            ]

            # Combine the queries with OR
            query = queries.pop()
            for item in queries:
                query |= item

            queryset = queryset.filter(query)

        return queryset

    def list(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        """
        Override the default list method to increase page size for users with many customers.
        """
        # Get the queryset and check the count
        queryset = self.get_queryset()
        total_count = queryset.count()

        # If the user has a lot of customers, use a larger page size
        if total_count > 40:
            # Temporarily override the page size
            self.pagination_class.page_size = 100

        # Use the standard list implementation
        response = super().list(request, *args, **kwargs)

        # Add the total count to the response for client information
        if hasattr(response, 'data') and isinstance(response.data, dict):
            response.data['total_count'] = total_count

        return response

    @transaction.atomic
    def update(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        try:
            instance = self.get_object()
            partial = kwargs.pop('partial', False)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to update customer. Please check your input.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

    def perform_update(self, serializer: Serializer) -> None:
        serializer.save()

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

class CollectionViewSet(BaseViewSet):
    queryset = Collection.objects.select_related('customer', 'author')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['collection_time', 'milk_type', 'collection_date']
    search_fields = ['customer__name']
    ordering_fields = [
        'collection_date', 'created_at', 'liters', 'kg',
        'fat_percentage', 'fat_kg', 'snf_percentage', 'snf_kg',
        'rate', 'amount'
    ]
    ordering = ['-collection_date', '-created_at']
    filterset_class = CollectionFilter

    def get_serializer_class(self) -> Type[Serializer]:
        if self.action == 'list':
            return CollectionListSerializer
        return CollectionDetailSerializer

    @transaction.atomic
    def create(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        collection_date = request.data.get('collection_date')
        customer_id = request.data.get('customer')
        base_snf_percentage = Decimal(str(request.data.get('base_snf_percentage', '9.0')))
        kg_amount = Decimal(str(request.data.get('kg', '0')))

        # Validate base_snf_percentage range
        if base_snf_percentage < Decimal('8.0') or base_snf_percentage > Decimal('9.5'):
            return Response(
                {'error': 'Base SNF percentage must be between 8.0 and 9.5'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            wallet = Wallet.objects.get(user=request.user)

            # Get collection fee settings
            collection_fee = getattr(settings, 'COLLECTION_FEE', {})

            # Check wallet balance if collection fee is enabled
            if collection_fee.get('ENABLED', False):
                # Calculate required balance based on kg
                per_kg_rate = Decimal(str(collection_fee.get('PER_KG_RATE', 0.02)))
                required_balance = (per_kg_rate * kg_amount).quantize(Decimal('0.001'))

                if required_balance > 0 and wallet.balance < required_balance:
                    return Response(
                        {
                            'error': 'Insufficient wallet balance. Please add money to your wallet to create new collections.',
                            'required_balance': str(required_balance),
                            'current_balance': str(wallet.balance),
                            'message': f'Balance required for collection fee ({per_kg_rate} per kg)'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
        except Wallet.DoesNotExist:
            return Response(
                {'error': 'No wallet found. Please contact support.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @transaction.atomic
    def update(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()

        # Check if collection can be edited
        if not instance.can_edit():
            edit_settings = getattr(settings, 'COLLECTION_EDIT', {})
            max_days = edit_settings.get('MAX_EDIT_DAYS', 7)
            max_edits = edit_settings.get('MAX_EDIT_COUNT', 1)

            days_since_creation = (timezone.now() - instance.created_at).days

            if instance.edit_count >= max_edits:
                return Response(
                    {
                        'error': f'This collection has already been edited {instance.edit_count} time(s). Maximum allowed edits is {max_edits}.',
                        'edit_count': instance.edit_count,
                        'max_edits': max_edits
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                return Response(
                    {
                        'error': f'This collection can no longer be edited. Collections can only be edited within {max_days} days of creation.',
                        'days_since_creation': days_since_creation,
                        'max_days': max_days
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
        header = ['DATE', 'WEIGHT','FAT KG.', 'SNF KG.', 'Amount (Rs.)']

        # Initialize grand totals
        grand_totals = {
            'total_kg': 0,
            'total_fat_kg': 0,
            'total_snf_kg': 0,
            'total_amount': 0,
            'purchase_amount': 0,
            'fat_percentage_sum': 0,
            'snf_percentage_sum': 0,
            'total_solid_weight': 0,
            'count': 0
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
            #final_amount = int(purchase_amount * Decimal('0.999'))

            # Update grand totals
            grand_totals['total_kg'] += daily_totals['total_kg']
            grand_totals['total_fat_kg'] += daily_totals['total_fat_kg']
            grand_totals['total_snf_kg'] += daily_totals['total_snf_kg']
            grand_totals['purchase_amount'] += purchase_amount
            #grand_totals['total_amount'] += final_amount
            #grand_totals['fat_percentage_sum'] += daily_totals['avg_fat_percentage']
            #grand_totals['snf_percentage_sum'] += daily_totals['avg_snf_percentage']
            grand_totals['total_solid_weight'] += date_collections.aggregate(total_solid=Sum('solid_weight'))['total_solid'] or 0
            grand_totals['count'] += 1

            daily_data.append([
                date['collection_date'].strftime('%d/%m/%Y'),
                f"{daily_totals['total_kg']:.2f}",
                #f"{daily_totals['avg_fat_percentage']:.2f}",
                f"{daily_totals['total_fat_kg']:.3f}",
                #f"{daily_totals['avg_snf_percentage']:.2f}",
                f"{daily_totals['total_snf_kg']:.3f}",
                f"{purchase_amount:.2f}",
                #f"{final_amount:.2f}"
            ])

        rows_per_page = 25
        total_rows = len(daily_data)
        total_pages = (total_rows + rows_per_page - 1) // rows_per_page

        col_widths = [
            doc.width * 0.20,   # DATE - wider for better readability
            doc.width * 0.20,   # WEIGHT - wider for better readability
            doc.width * 0.20,   # FAT KG - wider for better readability
            doc.width * 0.20,   # SNF KG - wider for better readability
            doc.width * 0.20    # Amount (Rs.) - wider for better readability
        ]

        # Process each page
        for page_num in range(total_pages):
            start_idx = page_num * rows_per_page
            end_idx = min((page_num + 1) * rows_per_page, total_rows)

            page_data = daily_data[start_idx:end_idx]

            if page_num == total_pages - 1:
                #avg_fat = grand_totals['fat_percentage_sum'] / grand_totals['count'] if grand_totals['count'] > 0 else 0
                #avg_snf = grand_totals['snf_percentage_sum'] / grand_totals['count'] if grand_totals['count'] > 0 else 0

                page_data.append([
                    'TOTAL:',
                    f"{grand_totals['total_kg']:.2f}",
                    #f"{avg_fat:.2f}",
                    f"{grand_totals['total_fat_kg']:.3f}",
                    #f"{avg_snf:.2f}",
                    f"{grand_totals['total_snf_kg']:.3f}",
                    f"{grand_totals['purchase_amount']:.2f}",
                    #f"{grand_totals['total_amount']:.2f}"
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

        # Initialize grand totals
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

            # Update grand totals
            grand_totals['total_weight'] += customer_totals['total_weight']
            grand_totals['total_fat_kg'] += customer_totals['total_fat_kg']
            grand_totals['total_snf_kg'] += customer_totals['total_snf_kg']
            grand_totals['purchase_amount'] += purchase_amount
            grand_totals['total_amount'] += final_amount
            grand_totals['total_solid_weight'] += customer_totals['total_solid_weight'] or 0
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

                if 'SolidWeight' not in styles:
                    styles.add(ParagraphStyle(
                        name='SolidWeight',
                        parent=styles['Normal'],
                        fontSize=11,
                        fontName='Courier-Bold',
                        alignment=0,  # Left alignment
                        leftIndent=0,  # Remove left indent to fully left align
                        spaceAfter=2
                    ))

                # Create a table with solid weight on left and total amount on right
                total_amount = grand_totals['total_amount']
                
                final_data = [
                    [
                        Paragraph(f"Solid Weight: {grand_totals['total_solid_weight']:.2f} kg", styles['SolidWeight']),
                        Paragraph(f"Total Amount: Rs. {total_amount:.2f}", styles['AmountDetail'])
                    ]
                ]
                
                final_table = Table(final_data, colWidths=[doc.width*0.5, doc.width*0.5])
                final_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),  # Left align solid weight
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),  # Right align total amount
                    ('VALIGN', (0, 0), (1, 0), 'MIDDLE'),  # Vertical alignment
                    ('FONTNAME', (0, 0), (1, 0), 'Courier-Bold'),  # Set font
                    ('FONTSIZE', (0, 0), (1, 0), 11),  # Set font size
                    ('BOTTOMPADDING', (0, 0), (1, 0), 4),  # Reduced bottom padding
                    ('TOPPADDING', (0, 0), (1, 0), 4),  # Reduced top padding
                ]))
                
                elements.append(final_table)

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
        # New column order as per requirements with CLR added after FAT%
        header = ['DATE', 'WEIGHT', 'FAT %', 'CLR', 'SNF %', 'FAT KG', 'FAT RT', 'SNF KG', 'SNF RT', 'MILK RT', 'AMOUNT']
        data.append(header)

        # Initialize totals
        totals = {
            'total_kg': 0,
            'total_fat_kg': 0,
            'total_snf_kg': 0,
            'total_amount': 0,
            'fat_percentage_sum': 0,
            'snf_percentage_sum': 0,
            'total_solid_weight': 0,
            'count': 0
        }

        for collection in collections.order_by('collection_date', 'collection_time'):
            # Add AM/PM based on collection_time
            time_suffix = "AM" if collection.collection_time == "morning" else "PM"
            row = [
                f"{collection.collection_date.strftime('%d/%m/%Y')} {time_suffix}",
                f"{collection.kg:.2f}",
                f"{collection.fat_percentage:.2f}",
                f"{collection.clr:.2f}" if collection.clr else "-",
                f"{collection.snf_percentage:.2f}",
                f"{collection.fat_kg:.3f}",
                f"{collection.fat_rate:.2f}" if collection.fat_rate else "-",
                f"{collection.snf_kg:.3f}",
                f"{collection.snf_rate:.2f}" if collection.snf_rate else "-",
                f"{collection.milk_rate:.2f}",
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
            totals['total_solid_weight'] += collection.solid_weight or 0
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
            "-",
            f"{totals['total_snf_kg']:.3f}",
            "-",
            "-",
            f"{totals['total_amount']:.2f}"
        ]
        data.append(totals_row)

        # Create table with specific column widths
        col_widths = [
            doc.width * 0.15,   # DATE - Increased width for date with AM/PM
            doc.width * 0.09,   # WEIGHT - slightly reduced
            doc.width * 0.08,   # FAT %
            doc.width * 0.08,   # CLR
            doc.width * 0.08,   # SNF %
            doc.width * 0.10,   # FAT KG
            doc.width * 0.07,   # FAT RT - slightly reduced
            doc.width * 0.10,   # SNF KG
            doc.width * 0.07,   # SNF RT - slightly reduced
            doc.width * 0.08,   # MILK RT
            doc.width * 0.10    # AMOUNT
        ]

        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Courier-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Courier'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Left align dates
            ('ALIGN', (-2, 1), (-2, -1), 'RIGHT'),  # Right align purchase amount
            ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),  # Right align final amount
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

        if 'SolidWeight' not in styles:
            styles.add(ParagraphStyle(
                name='SolidWeight',
                parent=styles['Normal'],
                fontSize=11,
                fontName='Courier-Bold',
                alignment=0,  # Left alignment
                leftIndent=0,  # Remove left indent to fully left align
                spaceAfter=2
            ))

        # Add spacer before amount details
        elements.append(Spacer(1, 10))

        # Add solid weight in its own row with full width
        elements.append(Paragraph(f"Solid Weight: {totals['total_solid_weight']:.2f} kg", styles['SolidWeight']))
        elements.append(Spacer(1, 5))

        # Create a table for the final calculations similar to pro_rata_report
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
            ('TOPPADDING', (0, 0), (2, -1), 4),    # Reduced top padding to 4
            ('BOTTOMPADDING', (0, 0), (2, -1), 4), # Reduced bottom padding to 4
        ]))

        elements.append(final_table)

        return elements

    @action(detail=False, methods=['get'], url_path='purchase-report')
    def purchase_report(self, request: HttpRequest) -> Response:
        collections = self.get_queryset().exclude(is_pro_rata=True).values(
            'collection_date'
        ).annotate(
            total_weight=Sum('kg'),
            total_fat_percentage=Avg('fat_percentage'),
            total_snf_percentage=Avg('snf_percentage'),
            total_fat_kg=Sum('fat_kg'),
            total_snf_kg=Sum('snf_kg'),
            total_amount=Sum('amount')
        ).order_by('collection_date')

        page = self.paginate_queryset(collections)
        if page is not None:
            return self.get_paginated_response(page)

        return Response(collections)

    @action(detail=False, methods=['get'])
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

        # Get collections for the date range (exclude pro-rata)
        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date
        ).exclude(is_pro_rata=True).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No collections found for the specified date range'},
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

    @action(detail=False, methods=['get'])
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

        # Get collections for the date range (exclude pro-rata)
        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date
        ).exclude(is_pro_rata=True).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No collections found for the specified date range'},
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

    @action(detail=False, methods=['get'])
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

        # Get collections for the date range (exclude pro-rata)
        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date
        ).exclude(is_pro_rata=True).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No collections found for the specified date range'},
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

    @action(detail=False, methods=['get'])
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

        # Get collections for the date range (exclude pro-rata)
        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date
        ).exclude(is_pro_rata=True).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No collections found for the specified date range'},
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

    @action(detail=False, methods=['get'])
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

        # Get collections for the customers in date range (exclude pro-rata)
        collections = Collection.objects.filter(
            author=request.user,
            customer_id__in=customer_ids,
            collection_date__gte=start_date,
            collection_date__lte=end_date
        ).exclude(is_pro_rata=True).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No collections found for the specified customers and date range'},
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

    @action(detail=False, methods=['get'], url_path='purchase-summary-report')
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

        collections = Collection.objects.filter(
            author=request.user,
            collection_date__gte=start_date,
            collection_date__lte=end_date
        ).exclude(is_pro_rata=True).select_related('customer')

        if not collections.exists():
            return Response(
                {'error': 'No collections found for the specified date range'},
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
            grand_totals['total_solid_weight'] += customer_totals['total_solid_weight'] or 0
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

        page = self.paginate_queryset(summary_data)
        if page is not None:
            return self.get_paginated_response(page)

        return Response({
            'summary_data': summary_data,
            'grand_totals': grand_totals
        })

class RawCollectionViewSet(BaseViewSet):
    queryset = RawCollection.objects.select_related('customer', 'author')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['collection_time', 'milk_type', 'collection_date']
    search_fields = ['customer__name']
    ordering_fields = [
        'collection_date', 'created_at', 'liters', 'kg',
        'fat_percentage', 'fat_kg', 'snf_percentage', 'snf_kg'
    ]
    ordering = ['-collection_date', '-created_at']
    filterset_class = RawCollectionFilter
    
    def get_queryset(self) -> QuerySet:
        # Override to filter out collections with milk rate
        queryset = super().get_queryset()
        return queryset.filter(is_milk_rate=False)
    
    def get_serializer_class(self) -> Type[Serializer]:
        if self.action == 'list':
            return RawCollectionListSerializer
        return RawCollectionDetailSerializer
    
    @transaction.atomic
    def create(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
                headers=headers
            )
        except ValidationError as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to create collection. Please check your input.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'An unexpected error occurred. Please try again.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @transaction.atomic
    def update(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)
        except ValidationError as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to update collection. Please check your input.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'An unexpected error occurred. Please try again.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['put', 'patch'], url_path='add-milk-rate')
    @transaction.atomic
    def add_milk_rate(self, request: HttpRequest, pk=None) -> Response:
        try:
            instance = self.get_object()
            if instance.is_milk_rate:
                return Response(
                    {
                        'error': 'Milk rate already added',
                        'detail': 'This collection already has a milk rate'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Ensure milk_rate is in the request data
            if 'milk_rate' not in request.data or not request.data['milk_rate']:
                return Response(
                    {
                        'error': 'Missing milk_rate',
                        'detail': 'The milk_rate field is required to add milk rate'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Use the RawCollectionMilkRateSerializer to handle the validation and update
            serializer = RawCollectionMilkRateSerializer(
                instance, 
                data=request.data, 
                partial=True,
                context={'request': request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            
            return Response(
                {
                    'message': 'Milk rate added successfully',
                    'detail': 'Collection data has been copied to regular collections'
                },
                status=status.HTTP_200_OK
            )
        except ValidationError as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to add milk rate. Please check your input.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    'error': str(e),
                    'detail': 'An unexpected error occurred. Please try again.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='with-milk-rate')
    def with_milk_rate(self, request: HttpRequest) -> Response:
        # Special endpoint to get collections with milk rate
        queryset = RawCollection.objects.select_related('customer', 'author').filter(
            author=request.user,
            is_active=True,
            is_milk_rate=True
        )
        
        # Apply filters
        for backend in list(self.filter_backends):
            queryset = backend().filter_queryset(self.request, queryset, self)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = RawCollectionMilkRateSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = RawCollectionMilkRateSerializer(queryset, many=True)
        return Response(serializer.data)