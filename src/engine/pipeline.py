from enum import Enum, auto

class PipelineState(Enum):
    PRE_SDD = auto()
    INTENT = auto()
    SPEC = auto()
    PLAN = auto()
    DEV = auto()
    POST_SDD = auto()
    AB_TEST = auto()

class PipelineEngine:
    def __init__(self):
        self.state = PipelineState.PRE_SDD
        
    def transition(self, next_state: PipelineState):
        self.state = next_state
        return True
