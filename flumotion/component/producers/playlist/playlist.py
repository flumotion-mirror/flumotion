# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2004,2005,2006,2007 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE.GPL" in the source distribution for more information.

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.

import gst
import gobject
import time

from twisted.internet import defer

from flumotion.common import errors, messages, log, fxml
from flumotion.component import feedcomponent

from flumotion.common.messages import N_

import smartscale
import singledecodebin
import playlistparser

T_ = messages.gettexter('flumotion')

def videotest_gnl_src(name, start, duration, priority):
    src = gst.element_factory_make('videotestsrc')
    # Set videotestsrc to all black.
    src.props.pattern = 2
    gnlsrc = gst.element_factory_make('gnlsource', name)
    gnlsrc.props.start = start
    gnlsrc.props.duration = duration
    gnlsrc.props.media_start = 0
    gnlsrc.props.media_duration = duration
    gnlsrc.props.priority = priority
    gnlsrc.add(src)

    return gnlsrc

def audiotest_gnl_src(name, start, duration, priority):
    src = gst.element_factory_make('audiotestsrc')
    # Set audiotestsrc to use silence.
    src.props.wave = 4 
    gnlsrc = gst.element_factory_make('gnlsource', name)
    gnlsrc.props.start = start
    gnlsrc.props.duration = duration
    gnlsrc.props.media_start = 0
    gnlsrc.props.media_duration = duration
    gnlsrc.props.priority = priority
    gnlsrc.add(src)

    return gnlsrc

def file_gnl_src(name, uri, caps, start, duration, offset, priority):
    src = singledecodebin.SingleDecodeBin(caps, uri)
    gnlsrc = gst.element_factory_make('gnlsource', name)
    gnlsrc.props.start = start
    gnlsrc.props.duration = duration
    gnlsrc.props.media_start = offset
    gnlsrc.props.media_duration = duration
    gnlsrc.props.priority = priority
    gnlsrc.add(src)

    return gnlsrc

class PlaylistProducerMedium(feedcomponent.FeedComponentMedium):
    def __init__(self, comp):
        feedcomponent.FeedComponentMedium.__init__(self, comp)

    def remote_add_playlist(self, data):
        self.comp.addPlaylist(data)

class PlaylistProducer(feedcomponent.FeedComponent):

    componentMediumClass = PlaylistProducerMedium

    def init(self):
        self.basetime = -1
        self.pipeline = None

        self._hasAudio = True
        self._hasVideo = True

        # The gnlcompositions for audio and video
        self.videocomp = None
        self.audiocomp = None

        self.videocaps = gst.Caps("video/x-raw-yuv;video/x-raw-rgb")
        self.audiocaps = gst.Caps("audio/x-raw-int;audio/x-raw-float")

        self._vsrcs = {} # { PlaylistItem -> gnlsource }
        self._asrcs = {} # { PlaylistItem -> gnlsource }

    def _buildAudioPipeline(self, pipeline, queue):
        audiorate = gst.element_factory_make("audiorate")
        audioconvert = gst.element_factory_make('audioconvert')
        audioresample = gst.element_factory_make('audioresample')
        outcaps = gst.Caps("audio/x-raw-int,channels=%d,rate=%d" % 
            (self._channels, self._samplerate))

        capsfilter = gst.element_factory_make("capsfilter")
        capsfilter.props.caps = outcaps

        pipeline.add(audiorate, audioconvert, audioresample, capsfilter)
        queue.link(audioconvert)
        audioconvert.link(audioresample)
        audioresample.link(audiorate)
        audiorate.link(capsfilter)

        return capsfilter.get_pad('src')

    def _buildVideoPipeline(self, pipeline, queue):
        outcaps = gst.Caps(
            "video/x-raw-yuv,width=%d,height=%d,framerate=%d/%d,"
            "pixel-aspect-ratio=1/1" % 
                (self._width, self._height, self._framerate[0], 
                 self._framerate[1]))

        cspace = gst.element_factory_make("ffmpegcolorspace")
        scaler = smartscale.SmartVideoScale()
        scaler.set_caps(outcaps)
        videorate = gst.element_factory_make("videorate")
        capsfilter = gst.element_factory_make("capsfilter")
        capsfilter.props.caps = outcaps

        pipeline.add(cspace, scaler, videorate, capsfilter)

        queue.link(cspace)
        cspace.link(scaler)
        scaler.link(videorate)
        videorate.link(capsfilter)
        return capsfilter.get_pad('src')

    def _buildPipeline(self):
        pipeline = gst.Pipeline()

        for mediatype in ['audio', 'video']:
            if (mediatype == 'audio' and not self._hasAudio) or (
                mediatype == 'video' and not self._hasVideo):
                continue

            composition = gst.element_factory_make("gnlcomposition", 
                mediatype + "-composition")

            queue = gst.element_factory_make("queue")
            identity = gst.element_factory_make("identity")
            identity.set_property("sync", True)
            identity.set_property("single-segment", True)
            identity.set_property("silent", True)

            pipeline.add(composition, identity, queue)

            def _padAddedCb(element, pad, target):
                self.debug("Pad added, linking")
                pad.link(target)
            composition.connect('pad-added', _padAddedCb, 
                identity.get_pad("sink"))
            identity.link(queue)

            if mediatype == 'audio':
                self.audiocomp = composition
                srcpad = self._buildAudioPipeline(pipeline, queue)
            else:
                self.videocomp = composition
                srcpad = self._buildVideoPipeline(pipeline, queue)

            feedername = 'feeder:%s:%s' % (self.name, mediatype)
            chunk = self.FEEDER_TMPL % {'name': feedername}
            binstr = "bin.("+chunk+" )"
            self.debug("Parse for media composition is %s", binstr)

            bin = gst.parse_launch(binstr)
            pad = bin.find_unconnected_pad(gst.PAD_SINK)
            ghostpad = gst.GhostPad(mediatype + "-feederpad", pad)
            bin.add_pad(ghostpad)

            pipeline.add(bin)
            srcpad.link(ghostpad)

        return pipeline

    def _createDefaultSources(self):
        if self._hasVideo:
            vsrc = videotest_gnl_src("videotestdefault", 0, 2**63 - 1, 
                2**31 - 1)
            self.videocomp.add(vsrc)

        if self._hasAudio:
            asrc = audiotest_gnl_src("videotestdefault", 0, 2**63 - 1, 
                2**31 - 1)
            self.audiocomp.add(asrc)

    def _setupClock(self, pipeline):
        # Configure our pipeline to use a known basetime and clock.
        clock = gst.SystemClock()
        # It doesn't matter too much what this basetime is, so long as we know
        # the value.
        self.basetime = clock.get_time()

        # We force usage of the system clock.
        pipeline.use_clock(clock)
        # Now we disable default basetime distribution
        pipeline.set_new_stream_time(gst.CLOCK_TIME_NONE)
        # And we choose our own basetime...
        self.debug("Setting basetime of %d", self.basetime)
        pipeline.set_base_time(self.basetime)

    def scheduleItem(self, item):
        """
        Schedule a given playlist item in our playback compositions.
        """
        start = item.timestamp - self.basetime
        self.debug("Starting item %s in %d seconds", item.uri, start/gst.SECOND)

        # If we schedule things to start before the current pipeline position,
        # gnonlin will adjust this to start now. However, it does this 
        # separately for audio and video, so we start from different points,
        # thus we're out of sync.
        # So, always start slightly in the future... 5 seconds seems to work
        # fine in practice.
        now = self.pipeline.query_position(gst.FORMAT_TIME)[0] + 5 * gst.SECOND

        if start < now:
            if start + item.duration < now:
                self.debug("Item too late; skipping entirely")
                return
            else:
                change = now - start
                self.debug("Starting item with offset %d", change)
                item.duration -= change
                item.offset += change
                start = now

        if self._hasVideo and item.hasVideo:
            self.debug("Adding video source with start %d, duration %d, "
                "offset %d", start, item.duration, item.offset)
            vsrc = file_gnl_src(None, item.uri, self.videocaps,
                start, item.duration, item.offset, 0)
            self.videocomp.add(vsrc)
            self._vsrcs[item] = vsrc
        if self._hasAudio and item.hasAudio:
            self.debug("Adding audio source with start %d, duration %d, "
                "offset %d", start, item.duration, item.offset)
            asrc = file_gnl_src(None, item.uri, self.audiocaps,
                start, item.duration, item.offset, 0)
            self.audiocomp.add(asrc)
            self._asrcs[item] = asrc
        self.debug("Done scheduling")

    def unscheduleItem(self, item):
        self.debug("Unscheduling item at uri %s", item.uri)
        if self._hasVideo and item.hasVideo:
            vsrc = self._vsrcs.pop(item)
            self.videocomp.remove(vsrc)
        if self._hasAudio and item.hasAudio: 
            asrc = self._asrcs.pop(item)
            self.audiocomp.remove(asrc)

    def adjustItemScheduling(self, item):
        if self._hasVideo and item.hasVideo:
            vsrc = self._vsrcs[item]
            vsrc.props.start = item.timestamp
            vsrc.props.duration = item.duration
            vsrc.props.media_duration = item.duration
        if self._hasAudio and item.hasAudio:
            asrc = self._asrcs[item]
            asrc.props.start = item.timestamp
            asrc.props.duration = item.duration
            asrc.props.media_duration = item.duration

    def addPlaylist(self, data):
        self.playlistparser.parseData(data)

    def create_pipeline(self):
        props = self.config['properties'];

        self._playlistfile = props.get('playlist', None)

        self._width = props.get('width', 320)
        self._height = props.get('height', 240)
        self._framerate = props.get('framerate', (15, 1))
        self._samplerate = props.get('samplerate', 44100)
        self._channels = props.get('channels', 2)

        self._hasAudio = props.get('audio', True)
        self._hasVideo = props.get('video', True)

        pipeline = self._buildPipeline() 
        self._setupClock(pipeline)

        self._createDefaultSources()

        self.connect_feeders(pipeline)
        return pipeline

    def do_start(self, clocking):
        self.link()

        playlist = playlistparser.Playlist(self)
        self.playlistparser = playlistparser.PlaylistXMLParser(playlist)
        try:
            if self._playlistfile:
                self.playlistparser.parseFile(self._playlistfile)
        except fxml.ParserError, e:
            self.warning("Failed to parse playlist file: %r", e)

        return defer.succeed(None)
        
    def do_stop(self):
        return feedcomponent.FeedComponent.do_stop(self)