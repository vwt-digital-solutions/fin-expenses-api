import datetime


def shift_to_business_days(pending: int):
    """

    :type pending: int
    
    :returns int
    """
    business_shift = 0
    business_day_delta = 0
    while business_day_delta <= pending:
        business_shift = business_shift + 1
        boundary_day = datetime.datetime.now() - datetime.timedelta(days=business_shift)
        if (boundary_day.weekday()) <= 5:
            business_day_delta = business_day_delta + 1
    return business_shift
