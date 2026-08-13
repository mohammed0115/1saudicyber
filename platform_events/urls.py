from django.urls import path

from . import views

app_name = 'platform_events'

urlpatterns = [
    path('events/', views.events, name='events'),
    path('webhooks/', views.webhook_subscriptions, name='webhooks'),
    path('status-recommendations/', views.status_recommendations, name='status-recommendations'),
    path('status-recommendations/<int:recommendation_id>/review/', views.review_recommendation, name='review-recommendation'),
]
