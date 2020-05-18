from re import findall
from math import ceil
from xml.etree import ElementTree as ET

from dashlivesim.dashlib.dash_proxy import DEFAULT_MINIMUM_UPDATE_PERIOD
from dashlivesim.dashlib import mpdprocessor
from dashlivesim.dashlib.timeformatconversions import make_timestamp, seconds_to_iso_duration


def get_mpd(dashProv):
    "Get the MPD corresponding to parameters in dashProv"
    cfg = dashProv.cfg
    if cfg.ext == ".period":
        mpd_filename = "%s/%s/%s" % (dashProv.content_dir, cfg.content_name, cfg.filename.split('+')[0])
        # Get the first part of the string only, which is the .manifest file name.
    elif cfg.ext == ".mpd":
        mpd_filename = "%s/%s/%s" % (dashProv.content_dir, cfg.content_name, cfg.filename)
    else:
        raise ValueError("Not a valid extension for manifest generation")
    mpd_input_data = dashProv.cfg_processor.get_mpd_data()
    nr_xlink_periods_per_hour = min(mpd_input_data['xlinkPeriodsPerHour'], 60)
    nr_periods_per_hour = min(mpd_input_data['periodsPerHour'], 60)
    # See exception description for explanation.
    if nr_xlink_periods_per_hour > 0:
        if nr_periods_per_hour == -1:
            raise Exception("Xlinks can only be created for a multiperiod service.")
        one_xlinks_for_how_many_periods = float(nr_periods_per_hour) / nr_xlink_periods_per_hour
        if one_xlinks_for_how_many_periods != int(one_xlinks_for_how_many_periods):
            raise Exception("(Number of periods per hour/ Number of xlinks per hour should be an integer.")
    if mpd_input_data['insertAd'] > 0 and nr_xlink_periods_per_hour < 0:
        raise Exception("Insert ad option can only be used in conjuction with the xlink option. To use the "
                        "insert ad option, also set use xlink_m in your url.")
    response = generate_dynamic_mpd(dashProv, mpd_filename, mpd_input_data, dashProv.now)
    # The following 'if' is for IOP 4.11.4.3 , deployment scenario when segments not found.
    if len(cfg.multi_url) > 0 and cfg.segtimelineloss:  # There is one specific baseURL with losses specified
        a_var, b_var = cfg.multi_url[0].split("_")
        dur1 = int(a_var[1:])
        dur2 = int(b_var[1:])
        total_dur = dur1 + dur2
        num_loop = int(ceil(60.0 / (float(total_dur))))
        now_mod_60 = dashProv.now % 60
        if a_var[0] == 'u' and b_var[0] == 'd':  # parse server up or down information
            for i in range(num_loop):
                if i * total_dur + dur1 < now_mod_60 <= (i + 1) * total_dur:
                    # Generate and provide mpd with the latest up time, so that last generated segment is shown
                    # and no new S element added to SegmentTimeline.
                    latestUptime = dashProv.now - now_mod_60 + (i * total_dur + dur1)
                    response = generate_dynamic_mpd(dashProv, mpd_filename, mpd_input_data, latestUptime)
                    break
                elif now_mod_60 == i * total_dur + dur1:
                    # Just before down time starts, add InbandEventStream to the MPD.
                    cfg.emsg_last_seg = True
                    response = generate_dynamic_mpd(dashProv, mpd_filename, mpd_input_data, dashProv.now)
                    cfg.emsg_last_seg = False

    if nr_xlink_periods_per_hour > 0:
        response = generate_response_with_xlink(response, cfg.ext, cfg.filename, nr_periods_per_hour,
                                                nr_xlink_periods_per_hour, mpd_input_data['insertAd'])
    return response


def generate_dynamic_mpd(dashProv, mpd_filename, in_data, now):
    "Generate the dynamic MPD."
    cfg = dashProv.cfg
    mpd_data = in_data.copy()
    if cfg.minimum_update_period_in_s is not None:
        mpd_data['minimumUpdatePeriod'] = seconds_to_iso_duration(cfg.minimum_update_period_in_s)
    else:
        mpd_data['minimumUpdatePeriod'] = DEFAULT_MINIMUM_UPDATE_PERIOD
    if cfg.media_presentation_duration is not None:
        mpd_data['mediaPresentationDuration'] = seconds_to_iso_duration(cfg.media_presentation_duration)
    mpd_data['timeShiftBufferDepth'] = seconds_to_iso_duration(cfg.timeshift_buffer_depth_in_s)
    mpd_data['timeShiftBufferDepthInS'] = cfg.timeshift_buffer_depth_in_s
    mpd_data['startNumber'] = cfg.adjusted_start_number
    mpd_data['publishTime'] = '%s' % make_timestamp(in_data['publishTime'])
    mpd_data['availabilityStartTime'] = '%s' % make_timestamp(in_data['availability_start_time_in_s'])
    mpd_data['duration'] = '%d' % in_data['segDuration']
    mpd_data['maxSegmentDuration'] = 'PT%dS' % in_data['segDuration']
    timescale = 1
    pto = 0
    mpd_data['presentationTimeOffset'] = cfg.adjusted_pto(pto, timescale)
    if mpd_data['suggested_presentation_delay_in_s'] is not None:
        spd = in_data['suggested_presentation_delay_in_s']
        mpd_data['suggestedPresentationDelay'] = \
            seconds_to_iso_duration(spd)
    if 'availabilityEndTime' in in_data:
        mpd_data['availabilityEndTime'] = make_timestamp(in_data['availabilityEndTime'])
    if cfg.stop_time is not None and (now > cfg.stop_time):
        mpd_data['type'] = "static"
    mpd_proc_cfg = {'scte35Present': (cfg.scte35_per_minute > 0),
                    'continuous': in_data['continuous'],
                    'segtimeline': in_data['segtimeline'],
                    'segtimeline_nr': in_data['segtimeline_nr'],
                    'utc_timing_methods': cfg.utc_timing_methods,
                    'utc_head_url': dashProv.utc_head_url,
                    'now': now}
    ll_data = {}  # Low-latency data
    if cfg.chunk_duration_in_s is None:
        mpd_data['availabilityTimeOffset'] = '%f' % in_data['availability_time_offset_in_s']
        if not cfg.availability_time_complete:
            mpd_data['availabilityTimeComplete'] = 'false'
    else:  # Set these values in the ll_data
        ll_data['availabilityTimeOffset'] = '%f' % in_data['availability_time_offset_in_s']
        ll_data['availabilityTimeComplete'] = 'false'

    if cfg.chunk_duration_in_s is not None and cfg.chunk_duration_in_s > 0:
        if len(mpd_proc_cfg['utc_timing_methods']) == 0:
            mpd_proc_cfg['utc_timing_methods'].append('httpiso')
        mpd_data['add_profiles'] = ['http://www.dashif.org/guidelines/low-latency-live-v5']
    full_url = dashProv.base_url + '/'.join(dashProv.url_parts)
    mpmod = mpdprocessor.MpdProcessor(mpd_filename, mpd_proc_cfg, cfg,
                                      full_url)
    period_data = generate_period_data(mpd_data, now, cfg)
    mpmod.process(mpd_data, period_data, ll_data)
    return mpmod.get_full_xml()


def generate_response_with_xlink(response, cfg, filename, nr_periods_per_hour, nr_xlink_periods_per_hour, insert_ad):
    "Convert the normally created response into a response which has xlinks"
    # This functions has two functionality : 1.For MPD and 2.For PERIOD.
    # 1. When the normally created .mpd file is fed to this function, it removes periods and inserts xlink for the
    # corresponding periods at that place.
    # 2. When the xlink period is accessed, it extracts the corresponding period from .mpd file this function generates,
    # adds some information and returns the appropriate .xml document to the java client.
    # pylint: disable=too-many-locals, too-many-statements
    if cfg == ".mpd":
        root = ET.fromstring(response)
        period_id_all = []
        for child in root.findall('{urn:mpeg:dash:schema:mpd:2011}Period'):
            period_id_all.append(child.attrib['id'])
        # period_id_all = findall('Period id="([^"]*)"', response)
        # Find all period ids in the response file.
        one_xlinks_for_how_many_periods = nr_periods_per_hour // nr_xlink_periods_per_hour
        period_id_xlinks = [x for x in period_id_all if int(x[1:]) % one_xlinks_for_how_many_periods == 0]
        # Periods that will be replaced with links.
        base_url = findall('<BaseURL>([^"]*)</BaseURL>', response)
        counter = 0
        for period_id in period_id_all:
            # Start replacing only if this condition is met.
            start_pos_period = response.find(period_id) - 12
            # Find the position in the string file of the period that has be replaced
            end_pos_period = response.find("</Period>", start_pos_period) + 9
            # End position of the corresponding period.
            if period_id in period_id_xlinks:
                counter += 1
                original_period = response[start_pos_period:end_pos_period]
                if insert_ad == 4:
                    xlink_period = '<Period xlink:href="http://vm1.dashif.org/dynamicxlink/invalid' \
                                   'url.php" xlink:actuate="onLoad" xmlns:xlink="http://www.w3.org/1999/xlink">' \
                                   '</Period>'
                elif insert_ad == 3:
                    xlink_period = '<Period xlink:href="http://vm1.dashif.org/dynamicxlink/ad.php' \
                                   '?id=6_ad_twoperiods_withremote" xlink:actuate="onLoad" xmlns:xlink="http://www.' \
                                   'w3.org/1999/xlink"></Period>'
                elif insert_ad == 2:
                    xlink_period = '<Period xlink:href="http://vm1.dashif.org/dynamicxlink/ad.php' \
                                   '?id=6_ad_twoperiods" xlink:actuate="onLoad" xmlns:xlink="http://www.w3.org/1999/' \
                                   'xlink"></Period>'
                elif insert_ad == 1 or insert_ad == 5:
                    xlink_period = '<Period xlink:href="http://vm1.dashif.org/dynamicxlink/ad.php?' \
                                   'id=6_ad" xlink:actuate="onLoad" xmlns:xlink="http://www.w3.org/1999/xlink">' \
                                   '</Period>'
                else:
                    xlink_period = '<Period xlink:href="%s%s+%s.period" xlink:actuate="onLoad" ' \
                                   'xmlns:xlink="http://www.w3.org/1999/xlink"></Period>' % (
                                       base_url[0], filename, period_id)
                if insert_ad > 0 and counter == 1:  # This condition ensures that the first period in the mpd is not
                    # replaced when the ads are enabled.
                    response = insert_asset_identifier(response, start_pos_period)
                    # Insert asset identifier, if the period is not replaced.
                    continue
                if insert_ad == 5:  # Add additional content for the default content
                    start_pos_period_contents = original_period.find('>') + 1
                    xlink_period = xlink_period[:-9] + '\n<!--Default content that will be played if the xlink is not' \
                                                       ' able to load.-->' + original_period[start_pos_period_contents:]
                response = response.replace(original_period, xlink_period)
            else:
                if insert_ad > 0:
                    response = insert_asset_identifier(response, start_pos_period)
    else:
        # This will be done when ".period" file is being requested
        # Start manipulating the original period so that it looks like .period in the static xlink file.
        filename = filename.split('+')[1]
        # Second part of string has the period id.
        start_pos_xmlns = response.find("xmlns=")
        end_pos_xmlns = response.find('"', start_pos_xmlns + 7) + 1
        start_pos_period = response.find(filename[:-7]) - 12
        # Find the position in the string file of the period that has be replaced.
        end_pos_period = response.find("</Period>", start_pos_period) + 9
        # End position of the corresponding period.
        original_period = response[start_pos_period:end_pos_period]
        original_period = original_period.replace('">', '" ' + response[start_pos_xmlns:end_pos_xmlns] + '>', 1)
        # xml_intro = '<?xml version="1.0" encoding="utf-8"?>\n'
        # response = xml_intro + original_period
        response = original_period
    return response


def generate_period_data(mpd_data, now, cfg):
    """Generate an array of period data depending on current time (now) and tsbd. 0 gives one period with start=1000h.

    mpd_data is changed (minimumUpdatePeriod)."""
    # pylint: disable=too-many-locals

    nr_periods_per_hour = min(mpd_data['periodsPerHour'], 60)
    if nr_periods_per_hour not in (-1, 0, 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60):
        raise Exception("Bad nr of periods per hour %d" % nr_periods_per_hour)

    seg_dur = mpd_data['segDuration']
    period_data = []
    ad_frequency = -1
    if mpd_data['insertAd'] > 0:
        ad_frequency = nr_periods_per_hour // mpd_data['xlinkPeriodsPerHour']

    if nr_periods_per_hour == -1:  # Just one period starting at at time start relative AST
        start = 0
        start_number = mpd_data['startNumber'] + start // seg_dur
        data = {'id': "p0", 'start': 'PT%dS' % start, 'startNumber': str(start_number),
                'duration': seg_dur, 'presentationTimeOffset': "%d" % mpd_data['presentationTimeOffset'],
                'start_s': start}
        period_data.append(data)
    elif nr_periods_per_hour == 0:  # nrPeriodsPerHour == 0, make one old period but starting 1000h after AST
        start = 3600 * 1000
        data = {'id': "p0", 'start': 'PT%dS' % start, 'startNumber': "%d" % (start // seg_dur),
                'duration': seg_dur, 'presentationTimeOffset': "%d" % start, 'start_s': start}
        period_data.append(data)
    else:  # nr_periods_per_hour > 0
        period_duration = 3600 // nr_periods_per_hour
        half_period_duration = period_duration // 2
        minimum_update_period_s = (half_period_duration - 5)
        if cfg.seg_timeline or cfg.seg_timeline_nr:
            minimum_update_period_s = cfg.seg_duration
        minimum_update_period = "PT%dS" % minimum_update_period_s
        mpd_data['minimumUpdatePeriod'] = minimum_update_period
        # this_period_nr = now // period_duration
        last_period_nr = (now + half_period_duration) // period_duration
        # this_period_start = this_period_nr * period_duration
        first_period_nr = (now - mpd_data['timeShiftBufferDepthInS'] - seg_dur) // period_duration
        counter = 0
        for period_nr in range(first_period_nr, last_period_nr+1):
            start_time = period_nr * period_duration
            data = {'id': "p%d" % period_nr, 'start': 'PT%dS' % start_time,
                    'startNumber': "%d" % (start_time//seg_dur), 'duration': seg_dur,
                    'presentationTimeOffset': period_nr*period_duration,
                    'start_s': start_time}
            if mpd_data['etpPeriodsPerHour'] > 0:
                # Check whether the early terminated feature is enabled or not.
                # If yes, then proceed.
                nr_etp_periods_per_hour = min(mpd_data['etpPeriodsPerHour'], 60)
                # Limit the maximum value to 60, same as done for the period.
                fraction_nr_periods_to_nr_etp = float(nr_periods_per_hour)/nr_etp_periods_per_hour
                if fraction_nr_periods_to_nr_etp != int(fraction_nr_periods_to_nr_etp):
                    raise Exception("(Number of periods per hour/ Number of etp periods per hour) "
                                    "should be an integer.")
                etp_duration = mpd_data['etpDuration']
                if etp_duration == -1:
                    etp_duration = period_duration // 2
                    # Default value
                    # If no etpDuration is specified, then we take a default values, i.e, half of period duration.
                if etp_duration > period_duration:
                    raise Exception("Duration of the early terminated period should be less that the duration of a "
                                    "regular period")
                if period_nr % fraction_nr_periods_to_nr_etp == 0:
                    data['etpDuration'] = etp_duration
                    data['period_duration_s'] = etp_duration

            if mpd_data['mpdCallback'] > 0:
                # Check whether the mpdCallback feature is enabled or not.
                # If yes, then proceed.
                nr_callback_periods_per_hour = min(mpd_data['mpdCallback'], 60)
                # Limit the maximum value to 60, same as done for the period.
                fraction_nr_periods_to_nr_callback = float(nr_periods_per_hour)/nr_callback_periods_per_hour
                if fraction_nr_periods_to_nr_callback != int(fraction_nr_periods_to_nr_callback):
                    raise Exception("(Number of periods per hour/ Number of callback periods per hour) "
                                    "should be an integer.")
                if period_nr % fraction_nr_periods_to_nr_callback == 0:
                    data['mpdCallback'] = 1
                    # If this period meets the condition, we raise a flag.
                    # We use the flag later to decide to put a mpdCallback element or not.

            period_data.append(data)
            if ad_frequency > 0 and ((period_nr % ad_frequency) == 0) and counter > 0:
                period_data[counter - 1]['periodDuration'] = 'PT%dS' % period_duration
                period_data[counter - 1]['period_duration_s'] = period_duration
            counter = counter + 1
            # print period_data
        for i, pdata in enumerate(period_data):
            if i != len(period_data) - 1:  # not last periodDuration
                if 'period_duration_s' not in pdata:
                    pdata['period_duration_s'] = period_duration
    return period_data


def insert_asset_identifier(response, start_pos_period):
    ad_pos = response.find(">", start_pos_period) + 1
    response = response[:ad_pos] + "\n<AssetIdentifier schemeIdUri=\"urn:org:dashif:asset-id:2013\" value=\"md:cid:" \
                                   "EIDR:10.5240%2f0EFB-02CD-126E-8092-1E49-W\"></AssetIdentifier>" + response[ad_pos:]
    return response
