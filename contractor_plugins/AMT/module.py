
from contractor.tscript.runner import ExternalFunction, Pause

MAX_POWER_SET_ATTEMPTS = 5


class set_power( ExternalFunction ):  # TODO: need a delay after each power command, at least 5 seconds, last ones could possibly be longer
  def __init__( self, foundation, state, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.connection_parameters = foundation.connection_parameters
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
      return ( 'set_power', { 'connection': self.connection_parameters, 'state': 'soft_off' } )
    else:
      return ( 'set_power', { 'connection': self.connection_parameters, 'state': self.desired_state } )

  def fromSubcontractor( self, data ):
    self.curent_state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.desired_state, self.curent_state, self.counter )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.desired_state = state[1]
    self.curent_state = state[2]
    self.counter = state[3]


class power_state( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.connection_parameters = foundation.connection_parameters
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
    return ( 'power_state', { 'connection': self.connection_parameters } )

  def fromSubcontractor( self, data ):
    self.state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.state )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.state = state[1]


class wait_for_poweroff( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.connection_parameters = foundation.connection_parameters
    self.curent_state = None

  @property
  def done( self ):
    return self.curent_state == 'off'

  @property
  def message( self ):
    return 'Waiting for Power off, curently "{0}"'.format( self.curent_state )

  def toSubcontractor( self ):
    return ( 'power_state', { 'connection': self.connection_parameters } )

  def fromSubcontractor( self, data ):
    self.curent_state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.curent_state )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.curent_state = state[1]


# plugin exports

TSCRIPT_NAME = 'amt'

TSCRIPT_FUNCTIONS = {
                    }

TSCRIPT_VALUES = {
                 }
