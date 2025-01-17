#! /bin/bash
timestamp="$(date +'%Y%m%d-%H%M%S')"
db="stitchv${timestamp}SET1.db"
dbzip="stitchv${timestamp}SET1db.zip"
log="log${timestamp}.txt"
stitcherDataInxightRepo="../stitcher-data-inxight"

#keep track of current time
curr_time=$(date +%s)

echo $(date) > $log

sbt stitcher/"runMain ncats.stitcher.impl.SRSJsonEntityFactory $db \"name=G-SRS, July 2018\" cache=data/hash.db $stitcherDataInxightRepo/files/dump-public-2018-07-19.gsrs"
echo 'gsrs:' $(( ($(date +%s) - $curr_time )/60 )) 'min' >> $log

# these add additional data for event calculator
sbt stitcher/"runMain ncats.stitcher.impl.MapEntityFactory $db data/dailymedrx.conf"
echo 'DailyMedRx:' $(( ($(date +%s) - $curr_time )/60 )) 'min' >> $log
sbt stitcher/"runMain ncats.stitcher.impl.MapEntityFactory $db data/dailymedrem.conf"
echo 'DailyMedRem:' $(( ($(date +%s) - $curr_time )/60 )) 'min' >> $log
sbt stitcher/"runMain ncats.stitcher.impl.MapEntityFactory $db data/dailymedotc.conf"
echo 'DailyMedOTC:' $(( ($(date +%s) - $curr_time )/60 )) 'min' >> $log
sbt stitcher/"runMain ncats.stitcher.impl.MapEntityFactory $db data/ob.conf"
echo 'OB:' $(( ($(date +%s) - $curr_time )/60 )) 'min' >> $log
sbt stitcher/"runMain ncats.stitcher.impl.MapEntityFactory $db data/ct.conf"
echo 'CT:' $(( ($(date +%s) - $curr_time )/60 )) 'min' >> $log

# now the stitching...
sbt stitcher/"runMain ncats.stitcher.tools.CompoundStitcher $db 1"
echo 'Stitching:' $(( ($(date +%s) - $curr_time )/60 )) 'min' >> $log

# calculate events
sbt stitcher/"runMain ncats.stitcher.calculators.EventCalculator $db 1"
echo 'EventCalculator:' $(( ($(date +%s) - $curr_time )/60 )) 'min' >> $log
echo $(date) >> $log

#zip up the directory
zip -r $dbzip $db

