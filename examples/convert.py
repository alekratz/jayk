from measurement.utils import guess as guess_unit
from measurement.measures import *
from measurement.base import MeasureBase
from jayk.cli.module import JaykMeta, jayk_command
import re

# Byte measurements
class Storage(MeasureBase):
    STANDARD_UNIT = 'byte'
    UNITS = {
        'bit': 1,
        'kbit': 1024,
        'mbit': 1024 ** 2,
        'gbit': 1024 ** 3,
        'tbit': 1024 ** 4,
        'pbit': 1024 ** 5,
        'byte': 8,
        'kb': 8 * 1024,
        'mb': 8 * 1024 ** 2,
        'gb': 8 * 1024 ** 3,
        'tb': 8 * 1024 ** 4,
        'pb': 8 * 1024 ** 5,
        'eb': 8 * 1024 ** 6,
        'zb': 8 * 1024 ** 7,
        'yb': 8 * 1024 ** 8,
    }
    ALIAS = {
        'b': 'byte',
        'kilobit': 'kbit',
        'megabit': 'mbit',
        'gigabit': 'gbit',
        'terabit': 'tbit',
        'petabit': 'pbit',
        'kilobyte': 'kb',
        'megabyte': 'mb',
        'gigabyte': 'gb',
        'terabyte': 'tb',
        'petabyte': 'pb',
        'exabyte':  'eb',
        'zetabyte': 'zb',
        'yottabyte':'yb',
    }


# Regular expression used for active conversion queries
CONVERT_RE = re.compile(r'(?P<X>[+-]?[0-9]+(\.[0-9]+)?) ?'
                        r'(?P<Xunit>[a-zA-Z\/_]+)'
                        r' to '
                        r'(?P<Yunit>[a-zA-Z\/_]+)')

# Regular expression used for passive (interjected) conversion queries
PASSIVE_RE = re.compile(r'(?P<Filter>[^0-9\s+-]?)'
                        r'(?P<X>[+-]?[0-9]+(\.[0-9]+)?) ?'
                        r'(?P<Xunit>[a-zA-Z\/_]+)\b')

# Strange aliases that refuse to be converted, or are converted in a weird way
UNIT_ALIASES = {
    'feet': 'ft',
    'in': 'inch',
    'km/h': 'km__hr',
    'km/hr': 'km__hr',
    'km/hour': 'km__hr',
    'mile': 'mi',  # this is only used by the unit_fixup method since sq_mile is not valid, but sq_mi is
}


def unit_fixup(unit_name):
    '''
    Helper method to fix unit names to be something that the guess_unit method can understand.
    '''
    global UNIT_ALIASES
    unit_name = unit_name.lower()
    # Add an underscore between the sq and the rest of the unit name if it starts with that
    if len(unit_name) >= 3 and unit_name[0:2] == 'sq' and unit_name[2] != '_':
        # also fixup the tail part
        unit_name = 'sq_' + unit_fixup(unit_name[2:])
    elif unit_name.startswith('sq_'):
        unit_name = 'sq_' + unit_fixup(unit_name[3:])
    # Strip following 's' as long as the unit is not 'inches'
    if unit_name.endswith('s') and unit_name != 'inches':
        unit_name = unit_name[:-1]
    return UNIT_ALIASES.get(unit_name, unit_name)


# Common conversions that are done in passive mode.
PASSIVE_CONVERSIONS = {
    #############
    # Distance

    # Feet are usually converted to meters and vice-versa
    'ft': 'm',
    'm': 'ft',
    # Inches are usually converted to centimeters and vice-versa
    'inch': 'cm',
    'cm': 'inch',
    'mm': 'inch',
    # Yards are usually converted to meters
    'yd': 'm',
    # Miles are usually converted to km and vice-versa
    'mi': 'km',
    'km': 'mi',

    #############
    # Speed

    # MPH and KPH are usually converted amongst each other
    'mi__hr': 'km__hr',
    'km__hr': 'mi__hr',

    #############
    # Temperature

    # C and F are usually converted amongst each other
    'c': 'f',
    'f': 'c',

    #############
    # Weight

    # kg and lbs are usually converted amongst each other
    'kg': 'lb',
    'lb': 'kg',

    # oz and grams are usually converted amongst each other
    'oz': 'g',
    'g': 'oz',
    # mg is usually converted to oz
    'mg': 'oz',
}

class Convert(metaclass=JaykMeta):

    def __init__(self, interject=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interject = interject

    def on_update_params(self, params):
        updates = ['interject']
        for p in updates:
            if p in params:
                self.debug("Updating parameter %s", p)
                setattr(self, p, params[p])

    def on_message(self, client, room, sender, msg):
        global PASSIVE_RE, PASSIVE_CONVERSIONS
        if not self.interject: return
        # normalize spaces
        msg = ' '.join(msg.split(' '))
        match = PASSIVE_RE.search(msg)
        # No match
        if match is None:
            return
        try:
            # Filter rule grabs any word character *before* the string; if anything was placed in
            # the filter, then we know that this isn't a string we want to inspect
            filt = match.group('Filter')
            if filt:
                return
            value = float(match.group('X'))
            unit = unit_fixup(match.group('Xunit'))
            measure = guess_unit(value, unit, measures=[Distance, Speed, Temperature, Weight])
        except ValueError:
            return
        unit = measure.unit
        self.debug("Best unit guess: %s", unit)
        if unit in PASSIVE_CONVERSIONS:
            to_unit = PASSIVE_CONVERSIONS[unit]
            try:
                to_value = getattr(measure, to_unit)
                to_measure = guess_unit(to_value, to_unit, measures=[Distance, Speed, Temperature, Weight])
                client.send_message(room, '{:.2f} {} ≈ {:.2f} {}'.format(measure.value, measure.unit, to_measure.value, to_measure.unit))
            except Exception as ex:
                self.error("Could not convert %s to %s: %s", measure, to_unit, ex)
                return

    @jayk_command("!convert")
    def convert(self, client, cmd, room, sender, msg):
        msg = ' '.join(msg.split()[1:])
        match = CONVERT_RE.match(msg)
        if match is None:
            nick = sender.nick
            client.send_message(room, '{}: Syntax is `!convert X UNIT_A to UNIT_B`')
            return
        try:
            # measurements in the correct order that we want them checked
            measures = [Distance, Area, Mass, Weight, Temperature, Time, Volume, Speed, Storage, Voltage, Current, Energy, Frequency, Resistance, Capacitance]
            value = float(match.group('X'))
            unit = unit_fixup(match.group('Xunit'))
            to_unit = unit_fixup(match.group('Yunit'))
            measure = guess_unit(value, unit, measures=measures)
            # use guess_unit to get the "proper" name of the unit; if it's illegal, it'll throw a ValueError
            to_measure = guess_unit(1, to_unit, measures=measures)
            self.debug("Best guess for %s: %s", to_unit, to_measure.unit)
            to_unit = to_measure.unit
            to_value = getattr(measure, to_unit)
            client.send_message(room, '{:.2f} {} ≈ {:.2f} {}'.format(value, unit, to_value, to_unit))
        except ValueError as ex:
            nick = sender.nick
            client.send_message(room, '{}: {}'.format(nick, ex))
        except Exception as ex:
            nick = sender.nick
            client.send_message(room, '{}: {}. Are you sure your units are compatible?'.format(nick, ex) + str(type(ex)))

    @staticmethod
    def author(): return 'intercal'

    @staticmethod
    def about(): return 'Use `!convert X UNIT_A to UNIT_B` to convert X number of UNIT_A to UNIT_B.'

    @staticmethod
    def name(): return 'Convert'

