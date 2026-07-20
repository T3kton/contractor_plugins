import re

from django.core.exceptions import ObjectDoesNotExist, ValidationError

from contractor.tscript.runner import ExternalFunction, ParameterError, Pause

NAME_REGEX = re.compile( r'^[a-zA-Z][a-zA-Z0-9\.\-_]*$' )
MAX_POWER_SET_ATTEMPTS = 5


# exported functions
class create( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = None
    self.in_rollback = False
    self.connection_parameters = {}
    self.vm_parameters = {}

  @property
  def done( self ):
    return self.uuid is not None

  @property
  def message( self ):
    if self.uuid is not None:
      if self.in_rollback:
        return 'VM Rolled Back'
      else:
        return 'VM Created'

    else:
      if self.in_rollback:
        return 'Waiting for VM Rollback'
      else:
        return 'Waiting for VM Creation'

  @property
  def value( self ):
    return self.uuid

  def setup( self, parms ):
    try:
      foundation = self.getScriptValue( 'foundation', 'foundation' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation: {0}'.format( e ) )

    try:
      libvirt_complex = self.getScriptValue( 'foundation', 'libvirt_complex' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation libvirt_complex: {0}'.format( e ) )

    self.connection_parameters = libvirt_complex.connection_parameters

    try:
      vm_spec = parms[ 'vm_spec' ]
    except KeyError:
      raise ParameterError( 'vm_spec', 'required' )

    if not isinstance( vm_spec, dict ):
      raise ParameterError( 'vm_spec', 'must be a dict' )

    interface_list = []
    for interface in foundation.networkinterface_set.all().order_by( 'physical_location' ):
      interface_list.append( { 'name': interface.name, 'network': interface.network.name } )

    self.vm_parameters = {  # the defaults
                           'disk_list': [ { 'name': 'sda', 'size': 10 } ],  # disk size in GiB, disk name mush match NAME_REGEX
                           'interface_list': interface_list,
                           'boot_order': [ 'network', 'hd' ]  # list of "fd", "hd", "cdrom", "network"
                         }

    if False:  # boot from iso instead
      self.vm_parameters[ 'disk_list' ].append( { 'name': 'cd', 'file': '/home/peter/Downloads/ubuntu-16.04.2-server-amd64.iso' } )
      self.vm_parameters[ 'boot_order' ][0] = 'cdrom'

    for key in ( 'cpu_count', 'memory_size' ):
      try:
        self.vm_parameters[ key ] = int( vm_spec[ key ] )
      except KeyError:
        raise ParameterError( 'vm_spec.{0}'.format( key ), 'required' )
      except ( ValueError, TypeError ):
        raise ParameterError( 'vm_spec.{0}'.format( key ), 'must be an integer' )

    if self.vm_parameters[ 'cpu_count' ] > 64 or self.vm_parameters[ 'cpu_count' ] < 1:
      raise ParameterError( 'cpu_count', 'must be from 1 to 64')
    if self.vm_parameters[ 'memory_size' ] > 1048510 or self.vm_parameters[ 'memory_size' ] < 512:  # in MiB
      raise ParameterError( 'memory_size', 'must be from 512 to 1048510' )

    try:
      self.vm_parameters[ 'name' ] = self.getScriptValue( 'foundation', 'locator' )
    except KeyError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation Locator: {0}'.format( e ) )

    if not NAME_REGEX.match( self.vm_parameters[ 'name' ] ):
      raise ParameterError( '<internal>', 'invalid vm name' )

    # for key in ( 'libvirt_domain_type', ):
    #   try:
    #     self.vm_parameters[ key[ 8: ] ] = vm_spec[ key ]
    #   except KeyError:
    #     pass

  def toSubcontractor( self ):
    print( f'to subcontractor Rollback "{self.in_rollback}"')
    if self.in_rollback:
      return ( 'create_rollback', { 'connection': self.connection_parameters, 'vm': self.vm_parameters } )
    else:
      return ( 'create', { 'connection': self.connection_parameters, 'vm': self.vm_parameters } )

  def fromSubcontractor( self, data ):
    print( f'from subcontractor Rollback "{self.in_rollback}"')
    if self.in_rollback:
      self.in_rollback = not data.get( 'rollback_done', False )
      print( f'to subcontractor Rollback is now "{self.in_rollback}"')
    else:
      self.uuid = data.get( 'uuid', None )

  def rollback( self ):
    if self.uuid is not None:
      raise ValueError( 'Unable to Rollback after vm has been created' )

    self.in_rollback = True

  def __getstate__( self ):
    return ( self.connection_parameters, self.vm_parameters, self.in_rollback, self.uuid )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.vm_parameters = state[1]
    self.in_rollback = state[2]
    self.uuid = state[3]


# other functions used by the libvirt foundation
class destroy( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = foundation.libvirt_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.libvirt_complex.connection_parameters
    self.complete = None

  @property
  def done( self ):
    return self.complete is True

  @property
  def message( self ):
    if self.complete is True:
      return 'VM Destroyed'
    else:
      return 'Waiting for VM Destruction'

  def toSubcontractor( self ):
    return ( 'destroy', { 'connection': self.connection_parameters, 'uuid': self.uuid, 'name': self.name } )

  def fromSubcontractor( self, data ):
    self.complete = True

  def __getstate__( self ):
    return ( self.connection_parameters, self.complete, self.name, self.uuid )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.complete = state[1]
    self.name = state[2]
    self.uuid = state[3]


class set_power( ExternalFunction ):  # TODO: need a delay after each power command, at least 5 seconds, last ones could possibly be longer
  def __init__( self, foundation, state, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = foundation.libvirt_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.libvirt_complex.connection_parameters
    self.desired_state = state
    self.curent_state = None
    self.counter = 0

  def run( self ):
    if self.desired_state != self.curent_state and self.counter > MAX_POWER_SET_ATTEMPTS:
      raise Pause( 'To Many Attempts to set power to "{0}", curently "{1}"'.format( self.desired_state, self.curent_state ) )

  @property
  def done( self ):
    return self.desired_state == self.curent_state

  @property
  def message( self ):
    return 'Power curently "{0}" waiting for "{1}", attempt {2} of {3}'.format( self.curent_state, self.desired_state, self.counter, MAX_POWER_SET_ATTEMPTS )

  def rollback( self ):
    self.counter = 0
    self.curent_state = None

  def toSubcontractor( self ):
    self.counter += 1
    if self.desired_state == 'off' and self.counter < 3:  # the first two times, do it nicely, after that, the hard way
      return ( 'set_power', { 'connection': self.connection_parameters, 'state': 'soft_off', 'uuid': self.uuid, 'name': self.name } )
    else:
      return ( 'set_power', { 'connection': self.connection_parameters, 'state': self.desired_state, 'uuid': self.uuid, 'name': self.name } )

  def fromSubcontractor( self, data ):
    self.curent_state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.uuid, self.name, self.desired_state, self.curent_state, self.counter )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.uuid = state[1]
    self.name = state[2]
    self.desired_state = state[3]
    self.curent_state = state[4]
    self.counter = state[5]


class power_state( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = foundation.libvirt_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.libvirt_complex.connection_parameters
    self.state = None

  @property
  def done( self ):
    return self.state is not None

  @property
  def message( self ):
    if self.state is None:
        return 'Retrieving for Power State'

    return 'Power State at "{0}"'.format( self.state )

  @property
  def value( self ):
    return self.state

  def toSubcontractor( self ):
    return ( 'power_state', { 'connection': self.connection_parameters, 'uuid': self.uuid, 'name': self.name } )

  def fromSubcontractor( self, data ):
    self.state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.uuid, self.name, self.state )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.uuid = state[1]
    self.name = state[2]
    self.state = state[3]


class wait_for_poweroff( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = foundation.libvirt_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.libvirt_complex.connection_parameters
    self.current_state = None

  @property
  def done( self ):
    return self.current_state == 'off'

  @property
  def message( self ):
    return 'Waiting for Power off, curently "{0}"'.format( self.current_state )

  def toSubcontractor( self ):
    return ( 'power_state', { 'connection': self.connection_parameters, 'uuid': self.uuid, 'name': self.name } )

  def fromSubcontractor( self, data ):
    self.current_state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.uuid, self.name, self.current_state )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.uuid = state[1]
    self.name = state[2]
    self.current_state = state[3]


class get_interface_map( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.foundation = foundation
    self.uuid = foundation.libvirt_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.libvirt_complex.connection_parameters
    self.interface_list = None

  @property
  def done( self ):
    return self.interface_list is not None

  @property
  def message( self ):
    if self.interface_list is not None:
      return 'Length of Interface Map: "{0}"'.format( len( self.interface_list ) )
    else:
      return 'Waiting for Interface Map'

  def setup( self, parms ):
    pass

  @property
  def value( self ):
    pos = 0
    result = {}
    for interface in self.foundation.networkinterface_set.all().order_by( 'physical_location' ):
      result[ interface.physical_location ] = self.interface_list[ pos ]
      pos += 1

    return result

  def toSubcontractor( self ):
    return ( 'get_interface_map', { 'connection': self.connection_parameters, 'uuid': self.uuid, 'name': self.name } )

  def fromSubcontractor( self, data ):
    self.interface_list = data[ 'interface_list' ]

  def __getstate__( self ):
    return ( self.foundation, self.connection_parameters, self.uuid, self.name, self.interface_list )

  def __setstate__( self, state ):
    self.foundation = state[0]
    self.connection_parameters = state[1]
    self.uuid = state[2]
    self.name = state[3]
    self.interface_list = state[4]


class set_interface_macs():
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.foundation = foundation

  def __call__( self, interface_map ):
    for physical_location in interface_map:
      try:
        iface = self.foundation.networkinterface_set.get( physical_location=physical_location )
      except ObjectDoesNotExist:
        raise ParameterError( 'interface_map', 'interface at "{0}" not found'.format( physical_location ) )

      iface.mac = interface_map[ physical_location ]

      try:
        iface.full_clean()
      except ValidationError as e:
        raise ParameterError( 'interface_map', 'Error saving interface "{0}": {1}'.format( physical_location, e ) )

      iface.save()


# plugin exports

TSCRIPT_NAME = 'libvirt'

TSCRIPT_FUNCTIONS = {
                      'create': create,
                    }

TSCRIPT_VALUES = {
                 }
