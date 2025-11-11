"""
AI Demand Forecasting using Facebook Prophet
"""
from sqlalchemy import func
from datetime import datetime, timedelta
import pandas as pd
from prophet import Prophet
import numpy as np

def prepare_forecast_data(db_session, Bill, Item, days=30):
    """
    Prepare historical data for forecasting
    Returns: DataFrame with columns: ds (date), y (quantity), item_id, item_name
    """
    # Get bills from last 6 months
    start_date = datetime.utcnow() - timedelta(days=180)
    
    bills = db_session.query(
        Bill.date,
        Bill.item_id,
        Bill.quantity,
        Item.name
    ).join(Item).filter(
        Bill.date >= start_date
    ).order_by(Bill.date).all()
    
    if not bills:
        return None
    
    # Convert to DataFrame
    data = []
    for bill in bills:
        # Handle both datetime and date objects
        if hasattr(bill.date, 'date'):
            date_val = bill.date.date()
        else:
            date_val = bill.date
        data.append({
            'ds': date_val,
            'y': bill.quantity,
            'item_id': bill.item_id,
            'item_name': bill.name
        })
    
    df = pd.DataFrame(data)
    return df

def forecast_demand(db_session, Bill, Item, days=30):
    """
    Forecast demand for next N days using Prophet
    Returns: dict with item_id as key, forecast data as value
    """
    df = prepare_forecast_data(db_session, Bill, Item, days)
    
    if df is None or len(df) == 0:
        return {}
    
    forecasts = {}
    
    # Group by item
    for item_id in df['item_id'].unique():
        item_df = df[df['item_id'] == item_id].copy()
        item_name = item_df['item_name'].iloc[0]
        
        if len(item_df) < 7:  # Need at least 7 data points
            continue
        
        # Prepare Prophet format
        prophet_df = item_df[['ds', 'y']].copy()
        prophet_df.columns = ['ds', 'y']
        
        try:
            # Create and fit model
            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.05
            )
            model.fit(prophet_df)
            
            # Make future dataframe
            future = model.make_future_dataframe(periods=days)
            forecast = model.predict(future)
            
            # Get only future predictions
            future_forecast = forecast.tail(days)
            
            forecasts[item_id] = {
                'item_name': item_name,
                'forecast': future_forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].to_dict('records'),
                'model': model
            }
        except Exception as e:
            print(f"Error forecasting for item {item_id}: {e}")
            continue
    
    return forecasts

def get_forecast_insights(db_session, Bill, Item, days=30):
    """
    Get text insights from forecasts in Tamil and English
    """
    forecasts = forecast_demand(db_session, Bill, Item, days)
    
    if not forecasts:
        return []
    
    insights = []
    
    for item_id, forecast_data in forecasts.items():
        item_name = forecast_data['item_name']
        forecast_records = forecast_data['forecast']
        
        if not forecast_records:
            continue
        
        # Calculate average predicted demand
        avg_predicted = np.mean([r['yhat'] for r in forecast_records])
        
        # Get recent actual average (last 30 days)
        recent_date = datetime.utcnow() - timedelta(days=30)
        recent_bills = db_session.query(Bill).filter(
            Bill.item_id == item_id,
            Bill.date >= recent_date
        ).all()
        
        if recent_bills:
            avg_actual = np.mean([b.quantity for b in recent_bills])
            
            if avg_actual > 0:
                change_percent = ((avg_predicted - avg_actual) / avg_actual) * 100
                
                # Generate insight
                if abs(change_percent) > 5:  # Only show significant changes
                    direction = "அதிகரிப்பு" if change_percent > 0 else "குறைவு"
                    direction_en = "increase" if change_percent > 0 else "decrease"
                    
                    insight = {
                        'item_name': item_name,
                        'tamil': f"அடுத்த {days} நாட்களில் {item_name} தேவையில் {abs(change_percent):.1f}% {direction} எதிர்பார்க்கப்படுகிறது.",
                        'english': f"Next {days} days forecast: {item_name} demand expected to {direction_en} by {abs(change_percent):.1f}%.",
                        'change_percent': change_percent,
                        'avg_predicted': avg_predicted,
                        'avg_actual': avg_actual
                    }
                    insights.append(insight)
    
    # Sort by absolute change percentage
    insights.sort(key=lambda x: abs(x['change_percent']), reverse=True)
    
    return insights

