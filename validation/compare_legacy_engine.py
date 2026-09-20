from __future__ import annotations

from arterial_analysis.engine import AnalysisSettings, SegmentInput, analyze_segment

rows=[
    ("1순환로 선프라자→방서",2.5,4,8,8,160,59,986,1,2,16,40.1899024293,"B",34.6226934114,.6260833930,1.7635307355,43.9368462223),
    ("1순환로 선프라자←방서",1.2,3,7,8,160,59,1505,1,2,9,31.4492127086,"C",36.3526794426,4.4286668128,2.9124468149,50.9643289588),
    ("단재로 방서→지북",1.0,2,3,4,160,67,1288,1,2,11,37.2679415651,"C",30.6845225756,.9345048953,.8418367347,38.5977687207),
    ("단재로 방서←지북",1.0,2,5,4,160,32,584,1,2,18,24.8491675555,"D",52.5961897647,.8028667217,8.9557739558,72.8740683951),
    ("중고개로 용암→동남",1.0,4,6,6,160,57,996,1,2,12,35.0830971645,"C",35.6752048775,.6900989671,1.1131725417,44.6135173618),
    ("중고개로 용암←동남",1.6,4,6,6,160,37,637,1,2,19,32.1536708406,"C",47.8713104410,.6197839593,5.8743762204,63.9397327089),
    ("목련로 지북→동남",1.9,4,3,2,160,94,704,1,3,10,53.6304267822,"A",14.3511667615,.0601782641,.0579623341,17.3395407121),
    ("목련로 지북←동남",2.5,5,2,2,160,27,667,1,3,15,35.8761989745,"C",56.0753922311,.3989281160,3.1732972909,70.8626960842),
]

def calculate(row, *, queue: bool, force_type_ii: bool):
    name,length,bus,access,crossing,cycle,green,volume,phf,lanes,qb,*_=row
    segment=SegmentInput(uid=name,comparison_id=name,scenario="현황",year=2026,road_name=name,length_km=length,report_length_km=length,cycle_s=cycle,green_s=green,main_volume=volume,report_volume=volume,phf=phf,lanes=lanes,functional_class="중간규격",bus_stops=bus,access_points=access,crossing_signals=crossing,coordinated=False,initial_queue=qb if queue else 0,arterial_type_override="유형 II" if force_type_ii else "자동")
    return analyze_segment(segment,AnalysisSettings())

print("구간\tExcel속도\tExcelLOS\t요청항목만속도\t현행유형\t숨은Qb포함속도\t편람해석속도\t편람해석LOS\t편람유형\tfcw\td1\td2\td3\t총지체\t속도차(편람-Excel)")
for row in rows:
    requested=calculate(row,queue=False,force_type_ii=False)
    current=calculate(row,queue=True,force_type_ii=False)
    guideline=calculate(row,queue=True,force_type_ii=True)
    print("\t".join(map(str,[row[0],f"{row[11]:.2f}",row[12],f"{requested.speed_kmh:.2f}",requested.arterial_type,f"{current.speed_kmh:.2f}",f"{guideline.speed_kmh:.2f}",guideline.los,guideline.arterial_type,f"{guideline.fcw:.2f}",f"{guideline.uniform_delay_s:.3f}",f"{guideline.incremental_delay_s:.3f}",f"{guideline.initial_queue_delay_s:.3f}",f"{guideline.control_delay_s:.3f}",f"{guideline.speed_kmh-row[11]:+.2f}"])))
