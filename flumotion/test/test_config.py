# -*- Mode: Python; test-case-name:flumotion.test.test_config -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2004,2005 Fluendo, S.L. (www.fluendo.com). All rights reserved.

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

from twisted.trial import unittest

from flumotion.common import config, registry, errors

registry.registry.addFromString("""
<registry>
  <components>
    <component name="foobie" type="test-component">
      <properties>
        <property name="one" type="string"/>
        <property name="two" type="int"/>
        <property name="three" type="float"/>
        <property name="four" type="xml"/>
        <property name="five" type="bool"/>
        <property name="six" type="long"/>
      </properties>
    </component>
  </components>
</registry>""")

class TestConfig(unittest.TestCase):
    def testParseEmpty(self):
        conf = config.FlumotionConfigXML(None, '<planet/>')
        self.failIf(conf.getPath())
        self.failUnless(conf.export())

    def testParseWrongConfig(self):
        self.assertRaises(config.ConfigError,
            config.FlumotionConfigXML, None, '<somethingorother/>')

    def testParseWrongSyntax(self):
        self.assertRaises(config.ConfigError,
            config.FlumotionConfigXML, None, 'planet/>')

    def testParseAtmosphere(self):
        conf = config.FlumotionConfigXML(None,
             """
             <planet>
               <atmosphere>
                 <component name="component-name" type="test-component"/>
               </atmosphere>
             </planet>""")
        self.failUnless(conf.atmosphere)
        self.failUnless(conf.atmosphere.components)
        self.assertEquals(len(conf.atmosphere.components), 1)
        self.failUnless(conf.atmosphere.components['component-name'])
        self.assertEquals(conf.atmosphere.components['component-name'].name,
            "component-name")

    def testParseWrongAtmosphere(self):
        xml = """
             <planet>
               <atmosphere>
                 <somethingwrong name="component-name" type="test-component"/>
               </atmosphere>
             </planet>"""
        self.assertRaises(config.ConfigError,
            config.FlumotionConfigXML, None, xml)
 
    def testParseComponent(self):
        conf = config.FlumotionConfigXML(None,
             """
             <planet>
               <flow name="default">
                 <component name="component-name" type="test-component"/>
               </flow>
             </planet>
             """)

        flow = conf.flows[0]
        self.failUnless(flow.components.has_key('component-name'))
        component = flow.components['component-name']
        self.assertEquals(component.name, 'component-name')
        self.assertEquals(component.getName(), 'component-name')
        self.assertEquals(component.type, 'test-component')
        self.assertEquals(component.getType(), 'test-component')
        self.assertEquals(component.getParent(), 'default')
        self.assertEquals(component.getWorker(), None)
        dict = component.getConfigDict()
        self.assertEquals(dict.get('name'), 'component-name', dict['name'])
        self.assertEquals(dict.get('type'), 'test-component', dict['type'])
        
    def testParseManager(self):
        conf = config.FlumotionConfigXML(None,
             """
             <planet>
               <manager name="aname">
                 <host>mymachine</host>
                 <port>7000</port>
                 <transport>tcp</transport>
                 <debug>5</debug>
                 <component name="component-name" type="test-component"/>
               </manager>
             </planet>""")
        self.failUnless(conf.manager)
        self.failUnless(conf.manager.bouncer)
        self.failUnless(conf.manager.bouncer.name)
        self.assertEquals(conf.manager.bouncer.name, "component-name")

    def testParseError(self):
        xml = '<planet><bad-node/></planet>'
        self.assertRaises(config.ConfigError,
                          config.FlumotionConfigXML, None, xml)

    def testParseComponentError(self):
        xml = """<planet>
            <flow name="default"><component name="unused" type="not-existing"/></flow>
            </planet>"""
        self.assertRaises(errors.UnknownComponentError,
            config.FlumotionConfigXML, None, xml)

        xml = """<planet>
              <flow name="default">
                <component type="not-named"/>
              </flow>
            </planet>"""
        self.assertRaises(config.ConfigError,
                          config.FlumotionConfigXML, None, xml)

        xml = """<planet>
              <flow name="default">
                <component name="not-typed"/>
              </flow>
            </planet>"""
        self.assertRaises(config.ConfigError,
                          config.FlumotionConfigXML, None, xml)
        
    def testParseFlowError(self):
        xml = """<planet>
            <flow><component name="unused" type="not-existing"/></flow>
            </planet>"""
        self.assertRaises(config.ConfigError,
            config.FlumotionConfigXML, None, xml)

        xml = """<planet>
              <flow name="manager">
                <component name="unused" type="not-existing"/>
              </flow>
            </planet>"""
        self.assertRaises(config.ConfigError,
            config.FlumotionConfigXML, None, xml)

        xml = """<planet>
              <flow name="atmosphere">
                <component name="unused" type="not-existing"/>
              </flow>
            </planet>"""
        self.assertRaises(config.ConfigError,
            config.FlumotionConfigXML, None, xml)

        xml = """<planet>
              <flow name="wrongcomponentnode">
                <wrongnode name="unused" type="not-existing"/>
              </flow>
            </planet>"""
        self.assertRaises(config.ConfigError,
            config.FlumotionConfigXML, None, xml)


    def testParseManagerError(self):
        xml = """<planet><manager>
            <component name="first" type="test-component"></component>
            <component name="second" type="test-component"></component>
            </manager></planet>"""
        self.assertRaises(config.ConfigError,
                          config.FlumotionConfigXML, None, xml)

        xml = """<planet>
               <manager name="aname">
                 <port>notanint</port>
               </manager>
             </planet>"""
        self.assertRaises(config.ConfigError,
                          config.FlumotionConfigXML, None, xml)

        xml = """<planet>
               <manager name="aname">
                 <transport>notatransport</transport>
               </manager>
             </planet>"""
        self.assertRaises(config.ConfigError,
                          config.FlumotionConfigXML, None, xml)
  
        xml = """<planet>
               <manager name="aname">
                 <notanode/>
               </manager>
             </planet>"""
        self.assertRaises(config.ConfigError,
                          config.FlumotionConfigXML, None, xml)
   
    def testParseProperties(self):
        planet = config.FlumotionConfigXML(None,
             """<planet><flow name="default">
             <component name="component-name" type="test-component">
               <one>string</one>
               <two>1</two>
               <three>2.5</three>
               <four attr="attr-value">value</four>
               <five>True</five>
               <six>3981391981389138998131389L</six>
             </component></flow>
             </planet>""")
        flow = planet.flows[0]
        component = flow.components['component-name']
        conf = component.getConfigDict()
        self.assertEquals(conf.get('one'), 'string')
        self.assertEquals(conf.get('two'), 1)
        self.assertEquals(conf.get('three'), 2.5)
        custom = conf.get('four')
        self.failUnless(custom)
        self.assertEquals(getattr(custom, 'data', None), 'value')
        self.assertEquals(getattr(custom, 'attr', None), 'attr-value')
        self.failUnless(conf.get('five'))
        self.assertEquals(conf.get('six'), 3981391981389138998131389L)

    def testGetComponentEntries(self):
        conf = config.FlumotionConfigXML(None,
             """
             <planet>
               <atmosphere>
                 <component name="atmocomp" type="test-component"/>
               </atmosphere>
               <flow name="default">
                 <component name="flowcomp" type="test-component"/>
               </flow>
             </planet>
             """)
        entries = conf.getComponentEntries()
        self.failUnless(entries.has_key('/atmosphere/atmocomp'))
        self.failUnless(entries.has_key('/default/flowcomp'))

    def testGetComponentEntriesWrong(self):
        xml = """
             <planet>
               <flow name="atmosphere">
                 <component name="flowcomp" type="test-component"/>
               </flow>
             </planet>
             """
        self.assertRaises(config.ConfigError, config.FlumotionConfigXML, None,
            xml)



