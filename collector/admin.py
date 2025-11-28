from django.contrib import admin
from .models import Customer, Collection, MarketMilkPrice, DairyInformation, RawCollection, ProRataRateChart, FatStepUpRate, SnfStepDownRate
from .youtube_channel_models import YouTubeChannelLink

@admin.register(MarketMilkPrice)
class MarketMilkPriceAdmin(admin.ModelAdmin):
    list_display = ('price', 'author', 'is_active', 'created_at')
    list_filter = ('is_active', 'author')
    search_fields = ('price',)

    def get_queryset(self, request):
        return MarketMilkPrice.all_objects.all()

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('customer_id', 'name', 'phone', 'author', 'is_active')
    list_filter = ('is_active', 'author')
    search_fields = ('name', 'phone', 'customer_id')
    list_per_page = 20

    def get_queryset(self, request):
        return Customer.all_objects.all()

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'collection_date', 'collection_time', 
                   'milk_type', 'measured', 'liters', 'kg', 
                   'fat_percentage','fat_kg', 'snf_percentage','snf_kg', 'milk_rate', 
                   'amount', 'solid_weight', 'base_fat_percentage', 'base_snf_percentage', 'author', 'is_active')
    list_filter = ('is_active', 'collection_time', 'milk_type', 
                  'measured', 'collection_date', 'author')
    search_fields = ('customer__name',)
    date_hierarchy = 'collection_date'
    list_per_page = 20

    def get_queryset(self, request):
        return Collection.all_objects.all().select_related(
            'customer', 'author'
        )

@admin.register(DairyInformation)
class DairyInformationAdmin(admin.ModelAdmin):
    list_display = ('dairy_name', 'dairy_address', 'rate_type', 'author', 'is_active', 'created_at')
    list_filter = ('rate_type', 'is_active', 'author')
    search_fields = ('dairy_name', 'dairy_address')
    ordering = ('-created_at',)

    def get_queryset(self, request):
        qs = DairyInformation.all_objects.all()
        if not request.user.is_superuser:
            qs = qs.filter(author=request.user)
        return qs

    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.author = request.user
        super().save_model(request, obj, form, change)


class FatStepUpRateInline(admin.TabularInline):
    model = FatStepUpRate
    extra = 1


class SnfStepDownRateInline(admin.TabularInline):
    model = SnfStepDownRate
    extra = 1


@admin.register(ProRataRateChart)
class ProRataRateChartAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'is_active', 'created_at')
    list_filter = ('is_active', 'author')
    ordering = ('-created_at',)
    inlines = [FatStepUpRateInline, SnfStepDownRateInline]

@admin.register(RawCollection)
class RawCollectionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'collection_date', 'collection_time', 
                   'milk_type', 'measured', 'liters', 'kg', 
                   'fat_percentage', 'fat_kg', 'snf_percentage', 'snf_kg',
                   'is_milk_rate', 'author', 'is_active')
    list_filter = ('is_active', 'collection_time', 'milk_type', 
                  'measured', 'collection_date', 'is_milk_rate', 'author')
    search_fields = ('customer__name',)
    date_hierarchy = 'collection_date'
    list_per_page = 20

    def get_queryset(self, request):
        return RawCollection.all_objects.all().select_related(
            'customer', 'author'
        )

@admin.register(YouTubeChannelLink)
class YouTubeChannelLinkAdmin(admin.ModelAdmin):
    list_display = ('link',)
    ordering = ('-created_at',)

    def get_queryset(self, request):
        qs = YouTubeChannelLink.all_objects.all()
        if not request.user.is_superuser:
            qs = qs.filter(author=request.user)
        return qs

    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.author = request.user
        super().save_model(request, obj, form, change)