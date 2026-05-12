import datetime

def format_date(timestamp):
    """
    Format a datetime object for display in frontend
    :param timestamp: datetime object
    :return: formatted date string
    """
    if not timestamp:
        return "N/A"
        
    # Check if it's already a string
    if isinstance(timestamp, str):
        return timestamp
        
    now = datetime.datetime.utcnow()
    diff = now - timestamp
    
    if diff.days == 0:
        # Same day formatting (show time)
        return timestamp.strftime('%I:%M %p')
    elif diff.days < 7:
        # Within the week (show day and time)
        return timestamp.strftime('%a, %I:%M %p')
    else:
        # Older messages (show full date)
        return timestamp.strftime('%b %d, %Y %I:%M %p')
