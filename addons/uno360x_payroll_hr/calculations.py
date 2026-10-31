from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

def totals(net, rate):
    try:n=Decimal(str(net));r=Decimal(str(rate))
    except (InvalidOperation,ValueError,TypeError) as exc:raise ValueError('Importe o porcentaje inválido.') from exc
    if not n.is_finite() or not r.is_finite() or n <= 0 or not 0 <= r < 100:
        raise ValueError('Importe o porcentaje inválido.')
    n=n.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    gross=(n/(1-r/100)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    return float(n),float(gross-n),float(gross)

def cutoff(day,first=15,second=30):
    first=int(first);second=int(second)
    if not 1 <= first < second <= 31:raise ValueError('Calendario de cortes inválido.')
    month=day.replace(day=1)
    for _ in range(2):
        candidates=[]
        for configured in (first,second):
            d=configured
            while True:
                try:candidate=month.replace(day=d);break
                except ValueError:d-=1
            if candidate>=day:candidates.append(candidate)
        if candidates:return min(candidates)
        month=month.replace(year=month.year+1,month=1) if month.month==12 else month.replace(month=month.month+1)
    raise ValueError('No se encontró corte.')

def statement_totals(net,rate,previous_net=0):
    if not previous_net:return totals(net,rate)
    previous=Decimal(str(previous_net))
    if not previous.is_finite() or previous<0:raise ValueError('Neto previo inválido.')
    current,_,_=totals(net,rate)
    _,_,oldgross=totals(previous_net,rate)
    _,_,newgross=totals(float(previous+Decimal(str(current))),rate)
    gross=(Decimal(str(newgross))-Decimal(str(oldgross))).quantize(Decimal('.01'))
    return current,float(gross-Decimal(str(current))),float(gross)

def dispatch_deadline(now,first=15,second=30,hour=10,minute=0):
    from datetime import timezone
    if not 0<=hour<=23 or not 0<=minute<=59:raise ValueError('Hora de corte inválida.')
    if scheduled_cutoff(now.date(),first,second) is None or (now.hour,now.minute)<(hour,minute):return None
    return now.replace(hour=hour,minute=minute,second=0,microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)

def scheduled_cutoff(day,first=15,second=30):
    from datetime import timedelta
    if not 1<=int(first)<int(second)<=31:raise ValueError('Calendario de cortes inválido.')
    for index,configured in enumerate((int(first),int(second))):
        number=configured
        while True:
            try:nominal=day.replace(day=number);break
            except ValueError:number-=1
        dispatch=nominal-timedelta(days=1) if index==1 and nominal.day==30 and nominal.weekday()==6 else nominal
        if dispatch==day:return nominal
    return None


def cedula_digits(value):
    value=(value or '').strip().replace('-','').replace(' ','')
    if len(value)!=11 or not value.isascii() or not value.isdigit() or len(set(value))==1:
        raise ValueError('Indique una cédula dominicana válida de 11 dígitos.')
    total=0
    for index,number in enumerate(value[:10]):
        digit=int(number)*(1 if index%2==0 else 2)
        total+=digit//10+digit%10
    if (10-total%10)%10!=int(value[-1]):
        raise ValueError('La cédula no supera la verificación de dígito de control.')
    return value

def csv_safe(value):
    value=str(value or '')
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value


def monthly_report_period(now):
    from datetime import timedelta
    if now.day<5 or (now.day==5 and now.hour<10):return None
    end=now.date().replace(day=1)
    start=(end-timedelta(days=1)).replace(day=1)
    return start,end
