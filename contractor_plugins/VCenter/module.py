import re

from django.core.exceptions import ObjectDoesNotExist, ValidationError

from contractor.tscript.runner import ExternalFunction, ParameterError, Pause, ExecutionError

NAME_REGEX = re.compile( r'^[a-zA-Z][a-zA-Z0-9\.\-_]*$' )
MAX_POWER_SET_ATTEMPTS = 5


# TODO: a complex "takeover" functoin that the VCA can call after it is set up (as a dependancy?) to become the vcenter_host for the complex

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
        return 'VM Rolled back'
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
      vcenter_complex = self.getScriptValue( 'foundation', 'vcenter_complex' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation vcenter_complex: {0}'.format( e ) )

    self.connection_parameters = vcenter_complex.connection_parameters

    self.vm_parameters = {}

    self.vm_parameters[ 'datacenter' ] = vcenter_complex.vcenter_datacenter
    self.vm_parameters[ 'cluster' ] = vcenter_complex.vcenter_cluster

    try:
      self.vm_parameters[ 'name' ] = self.getScriptValue( 'foundation', 'locator' )
    except KeyError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation Locator: {0}'.format( e ) )

    if not NAME_REGEX.match( self.vm_parameters[ 'name' ] ):
      raise ParameterError( 'invalid name' )

    for key in ( 'host', 'datastore' ):
      try:
        self.vm_parameters[ key ] = parms[ key ]
      except KeyError:
        raise ParameterError( key, 'required' )

    try:
      vm_spec = parms[ 'vm_spec' ]
    except KeyError:
      raise ParameterError( 'vm_spec', 'required' )

    if not isinstance( vm_spec, dict ):
      raise ParameterError( 'vm_spec', 'must be a dict' )

    # for now we will cary on CPU, Memeory, for OVAs evntually something will pull this info from the OVA
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

    # is this an OVA, if so, short cut, just deploy it
    ova = vm_spec.get( 'ova', None )
    if ova is not None:
      self.vm_parameters[ 'ova' ] = ova
      self.vm_parameters[ 'boot_order' ] = [ 'hdd' ]

      try:
        self.vm_parameters[ 'disk_provisioning' ] = vm_spec[ 'disk_provisioning' ]
      except KeyError:
        pass

      for key in ( 'vcenter_property_map', 'vcenter_deployment_option', 'vcenter_ip_protocol' ):
        try:
          self.vm_parameters[ key[ 8: ] ] = vm_spec[ key ]
        except KeyError:
          pass

      interface_list = []
      for interface in foundation.networkinterface_set.all().order_by( 'physical_location' ):
        interface_list.append( { 'name': interface.name, 'physical_location': interface.physical_location, 'network': interface.network.name } )

      self.vm_parameters[ 'interface_list' ] = interface_list
      return

    # is this an template deploy, if so, short cut, just deploy it
    template = vm_spec.get( 'template', None )
    if template is not None:
      self.vm_parameters[ 'template' ] = template
      self.vm_parameters[ 'boot_order' ] = [ 'hdd' ]

      for key in ( 'vcenter_hostname', 'vcenter_domain', 'vcenter_dnsserver_list', 'vcenter_dnssuffix_list', 'vcenter_property_map' ):
        try:
          self.vm_parameters[ key[ 8: ] ] = vm_spec[ key ]
        except KeyError:
          pass

      interface_list = []
      for interface in foundation.networkinterface_set.all().order_by( 'physical_location' ):
        address = interface.config[ 'address_list' ][0]

        item = { 'name': interface.name, 'physical_location': interface.physical_location, 'network': interface.network.name }
        item[ 'address' ] = address[ 'address' ]
        item[ 'netmask' ] = address[ 'netmask' ]
        if address[ 'gateway' ] is not None:
          item[ 'gateway' ] = address[ 'gateway' ]
        interface_list.append( item )

      self.vm_parameters[ 'interface_list' ] = interface_list
      return

    # not OVA/Template do scratch
    try:
      interface_type = vm_spec[ 'vcenter_network_interface_class' ]
    except KeyError:
      interface_type = 'E1000'

    interface_list = []
    for interface in foundation.networkinterface_set.all().order_by( 'physical_location' ):
      interface_list.append( { 'name': interface.name, 'physical_location': interface.physical_location, 'network': interface.network.name, 'type': interface_type } )

    try:
      disk_size = int( vm_spec.get( 'disk_size', 10 ) )
    except ( ValueError, TypeError ):
      raise ParameterError( 'vm_spec.disk_size', 'must be number' )
    if disk_size > 10240 or disk_size < 2:  # in GiB
      raise ParameterError( 'disk_size', 'must be from 2 to 10240' )  # is 10 TiB enough?

    self.vm_parameters[ 'disk_list' ] = [ { 'size': disk_size, 'name': 'sda', 'type': vm_spec.get( 'disk_provisioning', 'thin' ) } ]  # disk size in GiB, see _createDisk in subcontractor_plugsin/vcenter/lib.py
    self.vm_parameters[ 'interface_list' ] = interface_list
    self.vm_parameters[ 'boot_order' ] = [ 'net', 'hdd' ]  # list of 'net', 'hdd', 'cd', 'usb'

    if False:  # boot from iso instead
      self.vm_parameters[ 'disk_list' ].append( { 'name': 'cd', 'file': '/home/peter/Downloads/ubuntu-16.04.2-server-amd64.iso' } )
      self.vm_parameters[ 'boot_order' ] = [ 'cd', 'net', 'hdd' ]

    for key in ( 'vcenter_guest_id', 'vcenter_virtual_exec_usage', 'vcenter_virtual_mmu_usage', 'vcenter_virtual_vhv', 'vcenter_property_map' ):
      try:
        self.vm_parameters[ key[ 8: ] ] = vm_spec[ key ]
      except KeyError:
        pass

  def toSubcontractor( self ):
    if self.in_rollback:
      return ( 'create_rollback', { 'connection': self.connection_parameters, 'vm': self.vm_parameters } )
    else:
      return ( 'create', { 'connection': self.connection_parameters, 'vm': self.vm_parameters } )

  def fromSubcontractor( self, data ):  # TODO: really if these are missing or false, there is a problem
    if self.in_rollback:
      self.in_rollback = not data.get( 'rollback_done', False )
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


class host_list( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.host_list = None
    self.connection_parameters = {}
    self.datacenter = None
    self.cluster = None
    self.min_memory = None
    self.cpu_scaler = None
    self.memory_scaler = None

  @property
  def done( self ):
    return self.host_list is not None

  @property
  def message( self ):
    if self.host_list is not None:
      return 'Host List Length: "{0}"'.format( len( self.host_list ) )
    else:
      return 'Waiting for Host List'

  @property
  def value( self ):
    return self.host_list

  def setup( self, parms ):
    try:
      vcenter_complex = self.getScriptValue( 'foundation', 'vcenter_complex' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation vcenter_complex: {0}'.format( e ) )

    self.connection_parameters = vcenter_complex.connection_parameters
    self.datacenter = vcenter_complex.vcenter_datacenter
    self.cluster = vcenter_complex.vcenter_cluster

    for key in ( 'min_memory', 'min_cpu' ):  # memory in MB
      try:
        setattr( self, key, int( parms[ key ] ) )
      except KeyError:
        raise ParameterError( key, 'required' )
      except ( ValueError, TypeError ):
        raise ParameterError( key, 'must be an integer' )

    for key in ( 'cpu_scaler', 'memory_scaler' ):
      try:
        setattr( self, key, int( parms.get( key, 1 ) ) )
      except ( ValueError, TypeError ):
        raise ParameterError( key, 'must be an integer' )

  def toSubcontractor( self ):
    return ( 'host_list', { 'connection': self.connection_parameters, 'datacenter': self.datacenter, 'cluster': self.cluster, 'min_memory': self.min_memory, 'min_cpu': self.min_cpu, 'cpu_scaler': self.cpu_scaler, 'memory_scaler': self.memory_scaler } )

  def fromSubcontractor( self, data ):
    self.host_list = data[ 'host_list' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.datacenter, self.cluster, self.min_memory, self.min_cpu, self.cpu_scaler, self.memory_scaler, self.host_list )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.datacenter = state[1]
    self.cluster = state[2]
    self.min_memory = state[3]
    self.min_cpu = state[4]
    self.cpu_scaler = state[5]
    self.memory_scaler = state[6]
    self.host_list = state[7]


class create_datastore( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.complete = False
    self.connection_parameters = {}
    self.datacenter = None
    self.datastore_list = None

  @property
  def done( self ):
    return self.complete is True

  @property
  def message( self ):
    if self.complete is True:
      return 'Datastore Created'
    else:
      return 'Waiting for Datastore Creation'

  def setup( self, parms ):
    try:
      vcenter_complex = self.getScriptValue( 'foundation', 'vcenter_complex' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation vcenter_complex: {0}'.format( e ) )

    self.connection_parameters = vcenter_complex.connection_parameters
    self.datacenter = vcenter_complex.vcenter_datacenter

    try:
      self.host = self.getScriptValue( 'config', 'vcenter_hostname' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation vcenter_hostname: {0}'.format( e ) )

    try:
      self.name = parms[ 'name' ]
    except AttributeError:
      raise ParameterError( 'name', 'required' )

    try:
      self.model = parms[ 'model' ]
    except AttributeError:
      raise ParameterError( 'model', 'required' )

  def toSubcontractor( self ):
    return ( 'create_datastore', { 'connection': self.connection_parameters, 'datacenter': self.datacenter, 'host': self.host, 'name': self.name, 'model': self.model } )

  def fromSubcontractor( self, data ):
    self.complete = data.get( 'done', False )

  def __getstate__( self ):
    return ( self.connection_parameters, self.datacenter, self.host, self.name, self.model, self.complete )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.datacenter = state[1]
    self.host = state[2]
    self.name = state[3]
    self.model = state[4]
    self.complete = state[5]


class datastore_list( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.datastore_list = None
    self.connection_parameters = {}
    self.datacenter = None
    self.cluster = None
    self.host = None
    self.min_free_space = None
    self.name_regex = None

  @property
  def done( self ):
    return self.datastore_list is not None

  @property
  def message( self ):
    if self.datastore_list is not None:
      return 'Datastore List Length: "{0}"'.format( len( self.datastore_list ) )
    else:
      return 'Waiting for Datastore List'

  @property
  def value( self ):
    return self.datastore_list

  def setup( self, parms ):
    try:
      vcenter_complex = self.getScriptValue( 'foundation', 'vcenter_complex' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation vcenter_complex: {0}'.format( e ) )

    self.connection_parameters = vcenter_complex.connection_parameters
    self.datacenter = vcenter_complex.vcenter_datacenter
    self.cluster = vcenter_complex.vcenter_cluster

    try:
      self.host = parms.get( 'host' )
    except AttributeError:
      raise ParameterError( 'host', 'Required' )

    try:
      self.min_free_space = int( parms.get( 'min_free_space' ) )  # in GB
    except KeyError:
      raise ParameterError( 'min_free_space', 'required' )
    except ( ValueError, TypeError ):
      raise ParameterError( 'min_free_space', 'must be an integer' )

    self.name_regex = parms.get( 'name_regex', None )

  def toSubcontractor( self ):
    return ( 'datastore_list', { 'connection': self.connection_parameters, 'datacenter': self.datacenter, 'cluster': self.cluster, 'host': self.host, 'min_free_space': self.min_free_space, 'name_regex': self.name_regex } )

  def fromSubcontractor( self, data ):
    self.datastore_list = data[ 'datastore_list' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.datacenter, self.cluster, self.host, self.name_regex, self.min_free_space, self.datastore_list )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.datacenter = state[1]
    self.cluster = state[2]
    self.host = state[3]
    self.name_regex = state[4]
    self.min_free_space = state[5]
    self.datastore_list = state[6]


class network_list( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.network_list = None
    self.connection_parameters = {}
    self.datacenter = None
    self.cluster = None
    self.host = None
    self.min_free_space = None
    self.name_regex = None

  @property
  def done( self ):
    return self.network_list is not None

  @property
  def message( self ):
    if self.network_list is not None:
      return 'Network List Length: "{0}"'.format( len( self.network_list ) )
    else:
      return 'Waiting for Network List'

  @property
  def value( self ):
    return self.network_list

  def setup( self, parms ):
    try:
      vcenter_complex = self.getScriptValue( 'foundation', 'vcenter_complex' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation vcenter_complex: {0}'.format( e ) )

    self.connection_parameters = vcenter_complex.connection_parameters
    self.datacenter = vcenter_complex.vcenter_datacenter
    self.cluster = vcenter_complex.vcenter_cluster

    try:
      self.host = parms.get( 'host' )
    except AttributeError:
      raise ParameterError( 'host', 'Required' )

    self.name_regex = parms.get( 'name_regex', None )

  def toSubcontractor( self ):
    return ( 'network_list', { 'connection': self.connection_parameters, 'datacenter': self.datacenter, 'cluster': self.cluster, 'host': self.host, 'name_regex': self.name_regex } )

  def fromSubcontractor( self, data ):
    self.network_list = data[ 'network_list' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.datacenter, self.cluster, self.host, self.name_regex, self.network_list )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.datacenter = state[1]
    self.cluster = state[2]
    self.host = state[3]
    self.name_regex = state[4]
    self.network_list = state[5]


# other functions used by the vcenter foundation
class destroy( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = foundation.vcenter_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.vcenter_complex.connection_parameters
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
    return ( self.connection_parameters, self.uuid, self.name, self.complete )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.uuid = state[1]
    self.name = state[2]
    self.complete = state[3]


class set_power( ExternalFunction ):  # TODO: need a delay after each power command, at least 5 seconds, last ones could possibly be longer
  def __init__( self, foundation, state, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = foundation.vcenter_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.vcenter_complex.connection_parameters
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
      return ( 'set_power', { 'state': 'soft_off', 'connection': self.connection_parameters, 'uuid': self.uuid, 'name': self.name } )
    else:
      return ( 'set_power', { 'state': self.desired_state, 'connection': self.connection_parameters, 'uuid': self.uuid, 'name': self.name } )

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
    self.uuid = foundation.vcenter_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.vcenter_complex.connection_parameters
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
    self.uuid = foundation.vcenter_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.vcenter_complex.connection_parameters
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
    self.uuid = foundation.vcenter_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.vcenter_complex.connection_parameters
    self.interface_list = None

  @property
  def done( self ):
    return self.interface_list is not None

  @property
  def message( self ):
    if self.interface_list is not None:
      return 'Interface Map Length: "{0}"'.format( len( self.interface_list ) )
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


class execute( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = foundation.vcenter_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.vcenter_complex.connection_parameters
    self.username = None
    self.password = None
    self.dir = '/'
    self.command = None
    self.timeout = 300
    self.expected_rc = 0
    self.rc = None
    self.error = None

  @property
  def done( self ):
    return self.rc is not None or self.error is not None

  @property
  def message( self ):
    if self.rc is not None:
      return 'Eexecution returned "{0}"'.format( self.rc )
    else:
      return 'Waiting for Execution'

  def setup( self, parms ):
    for name in ( 'username', 'password', 'command' ):
      try:
        setattr( self, name, parms[ name ] )
      except KeyError:
        raise ParameterError( name, 'required' )

      try:
        self.dir = parms[ 'dir' ]
      except KeyError:
        pass

      for name in ( 'timeout', 'expected_rc' ):
        try:
          setattr( self, name, int( parms[ name ] ) )
        except ValueError:
          raise ParameterError( name, 'must be valid integer' )
        except KeyError:
          pass

  @property
  def value( self ):
    if self.error is not None:
      return ExecutionError( 'Execution error: "{0}"'.format( self.error ) )

    if self.rc != self.expected_rc:
      return ExecutionError( 'Command returned "{0}", expected "{1}"'.format( self.rc, self.expected_rc ) )
    else:
      return True

  def toSubcontractor( self ):
    program = '/bin/sh'
    args = '-c "{0}"'.format( self.command )
    return ( 'execute', { 'connection': self.connection_parameters, 'uuid': self.uuid, 'name': self.name, 'username': self.username, 'password': self.password, 'program': program, 'args': args, 'dir': self.dir, 'timeout': self.timeout } )

  def fromSubcontractor( self, data ):
    self.rc = data.get( 'rc', None )
    self.error = data.get( 'error', None )

  def __getstate__( self ):
    return ( self.connection_parameters, self.uuid, self.name, self.username, self.password, self.command, self.dir, self.expected_rc, self.rc, self.error )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.uuid = state[1]
    self.name = state[2]
    self.username = state[3]
    self.password = state[4]
    self.command = state[5]
    self.dir = state[6]
    self.expected_rc = state[7]
    self.rc = state[8]
    self.error = state[9]


class mark_as_template( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = foundation.vcenter_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.vcenter_complex.connection_parameters
    self.as_template = None
    self.complete = None

  @property
  def done( self ):
    return self.complete is True

  @property
  def message( self ):
    if self.complete is True:
      return 'VM Marked as Template'
    else:
      return 'Waiting VM to get Marked'

  def setup( self, parms ):
    try:
      self.as_template = bool( parms.get( 'as_template', True ) )
    except ValueError:
      raise ParameterError( 'as_template', 'must be boolean' )
    except KeyError:
      pass

  def toSubcontractor( self ):
    return ( 'mark_as_template', { 'connection': self.connection_parameters, 'uuid': self.uuid, 'name': self.name, 'as_template': self.as_template } )

  def fromSubcontractor( self, data ):
    self.complete = True

  def __getstate__( self ):
    return ( self.connection_parameters, self.uuid, self.name, self.as_template, self.complete )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.uuid = state[1]
    self.name = state[2]
    self.as_template = state[3]
    self.complete = state[4]


class export( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.uuid = foundation.vcenter_uuid
    self.name = foundation.locator
    self.connection_parameters = foundation.vcenter_complex.connection_parameters
    self.url = None
    self.location = None

  @property
  def done( self ):
    return self.location is not None

  @property
  def message( self ):
    if self.location is not None:
      return 'Exported to "{0}"'.format( self.location )
    else:
      return 'Waiting VM to be Exported'

  def setup( self, parms ):
    try:
      self.url = parms.get( 'url' )
    except KeyError:
      raise ParameterError( 'url', 'required' )

  @property
  def value( self ):
    return self.handle

  def toSubcontractor( self ):
    return ( 'export', { 'connection': self.connection_parameters, 'uuid': self.uuid, 'name': self.name, 'url': self.url } )

  def fromSubcontractor( self, data ):
    self.location = data[ 'location' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.uuid, self.name, self.url, self.location )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.uuid = state[1]
    self.name = state[2]
    self.url = state[3]
    self.location = state[4]


# plugin exports

TSCRIPT_NAME = 'vcenter'

TSCRIPT_FUNCTIONS = {
                      'create': create,
                      'host_list': host_list,
                      'create_datastore': create_datastore,
                      'datastore_list': datastore_list,
                    }

TSCRIPT_VALUES = {
                 }
