from django_filters import rest_framework as filters
from .models import Collection, RawCollection

class CollectionFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name='collection_date', lookup_expr='gte')
    date_to = filters.DateFilter(field_name='collection_date', lookup_expr='lte')
    min_rate = filters.NumberFilter(field_name='rate', lookup_expr='gte')
    max_rate = filters.NumberFilter(field_name='rate', lookup_expr='lte')
    min_amount = filters.NumberFilter(field_name='amount', lookup_expr='gte')
    max_amount = filters.NumberFilter(field_name='amount', lookup_expr='lte')

    class Meta:
        model = Collection
        fields = {
            'collection_time': ['exact'],
            'milk_type': ['exact'],
            'customer': ['exact'],
            'measured': ['exact'],
            'liters': ['gte', 'lte'],
            'kg': ['gte', 'lte'],
            'fat_percentage': ['gte', 'lte'],
            'fat_kg': ['gte', 'lte'],
            'clr': ['gte', 'lte'],
            'snf_percentage': ['gte', 'lte'],
            'snf_kg': ['gte', 'lte'],
            'fat_rate': ['exact'],
            'snf_rate': ['exact'],
        }

class RawCollectionFilter(filters.FilterSet):
    customer_name = filters.CharFilter(field_name='customer__name', lookup_expr='icontains')
    from_date = filters.DateFilter(field_name='collection_date', lookup_expr='gte')
    to_date = filters.DateFilter(field_name='collection_date', lookup_expr='lte')
    milk_type = filters.ChoiceFilter(choices=RawCollection.MILK_TYPE_CHOICES)
    collection_time = filters.ChoiceFilter(choices=RawCollection.TIME_CHOICES)

    class Meta:
        model = RawCollection
        fields = [
            'customer_name', 'from_date', 'to_date', 
            'milk_type', 'collection_time', 'is_milk_rate'
        ] 