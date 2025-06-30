from abc import ABC, abstractmethod
from typing import TypedDict, Dict, Any, Optional, List, Callable, Union
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command,interrupt
import uuid
import logging

logger = logging.getLogger(__name__)

class BaseWorkflowState(TypedDict):
    """Base state that all workflows should inherit from"""
    user_input: str
    current_step: str
    workflow_status: str
    error_message: Optional[str]

from abc import ABC, abstractmethod
from typing import TypedDict, Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass

@dataclass
class InterruptConfig:
    """Configuration for human interaction interrupts"""
    interrupt_type: str
    message: str
    instructions: str
    options: List[str]
    step_name: str
    validation_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]]
    state_update_fn: Callable[[Dict, Dict[str, Any]], Dict]
    
    def get_data_builder(self) -> Callable[[Dict], Dict[str, Any]]:
        """Return function to build interrupt data from state"""
        return lambda state: {
            "type": self.interrupt_type,
            "instructions": self.instructions,
            "options": self.options
        }

class BaseWorkflow(ABC):
    """Base class for all LangGraph workflows"""
    
    def __init__(self):
        self.memory = InMemorySaver()
        self.app = None
        self._interrupt_configs = self._register_interrupt_configs()
        self._build_workflow()
    
    # Remove @abstractmethod decorator and provide default implementation
    def _register_interrupt_configs(self) -> Dict[str, InterruptConfig]:
        """Register all interrupt configurations for this workflow
        
        Returns:
            Dict mapping interrupt type to InterruptConfig
        """
        return {}  # Default empty dictionary
    
    def create_human_interaction_node(self, interrupt_type: str):
        """Template method for creating human interaction nodes
        
        This follows the Template Method pattern - the algorithm is defined here,
        but specific behaviors are delegated to the InterruptConfig (Strategy pattern)
        """
        def interaction_node(state): 
            config = self._interrupt_configs.get(interrupt_type)
            if not config:
                raise ValueError(f"No interrupt config found for type: {interrupt_type}")
            
            # Template method steps:
            # 1. Update step
            state = self.update_step(state, config.step_name)
            
            # 2. Validate preconditions (can be overridden)
            validation_result = self._validate_preconditions(state, config)
            if validation_result:
                return validation_result
            
            # 3. Build interrupt data
            data_builder = config.get_data_builder()
            base_data = data_builder(state)
            
            # 4. Add custom data (hook for subclasses)
            custom_data = self._build_custom_interrupt_data(state, config)
            data = {**base_data, **custom_data}
            
            # 5. Create interrupt with validation
            validation_context = self._build_validation_context(state, config)
            result = self.create_interrupt(
                message=config.message,
                data=data,
                validation_fn=config.validation_fn,
                validation_context=validation_context
            )
            
            # 6. Handle validation result
            if result.get("valid", False):
                return config.state_update_fn(state, result)
            
            return result
        
        return interaction_node
    
    def _validate_preconditions(self, state: Dict, config: InterruptConfig) -> Optional[Dict]:
        """Hook for validating preconditions before creating interrupt
        
        Can be overridden by subclasses for custom validation
        """
        return None
    
    def _build_custom_interrupt_data(self, state: Dict, config: InterruptConfig) -> Dict[str, Any]:
        """Hook for adding custom data to interrupt
        
        Can be overridden by subclasses to add workflow-specific data
        """
        return {}
    
    def _build_validation_context(self, state: Dict, config: InterruptConfig) -> Dict[str, Any]:
        """Hook for building validation context
        
        Can be overridden by subclasses for custom validation context
        """
        return {}
    
    def get_state_class(self):
        """Return the TypedDict class for this workflow's state"""
        pass
    
    @abstractmethod
    def define_nodes(self):
        """Define all nodes for the workflow. Should return a dict of {node_name: node_function}"""
        pass
    
    @abstractmethod
    def define_edges(self, workflow: StateGraph):
        """Define edges and conditional edges for the workflow"""
        pass
    
    @abstractmethod
    def get_entry_point(self) -> str:
        """Return the entry point node name"""
        pass
    
    def _build_workflow(self):
        """Build the LangGraph workflow"""
        StateClass = self.get_state_class()
        workflow = StateGraph(StateClass)
        
        # Add nodes
        nodes = self.define_nodes()
        for node_name, node_func in nodes.items():
            workflow.add_node(node_name, node_func)
        
        # Set entry point
        workflow.set_entry_point(self.get_entry_point())
        
        # Define edges
        self.define_edges(workflow)
        
        # Compile the workflow with interrupt capability
        self.app = workflow.compile(
            checkpointer=self.memory,
            interrupt_before=[],  # Can be overridden by subclasses
            interrupt_after=[]    # Can be overridden by subclasses
        )
    
    async def run(self, user_input: str, thread_id: str = None) -> Dict[str, Any]:
        """Run the workflow and return clean structured result"""
        # Initialize state with user input
        initial_state = {"user_input": user_input}
        
        # Generate thread_id if not provided
        if not thread_id:
            thread_id = f"workflow_{uuid.uuid4()}"
        
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            # Run the workflow
            result = await self.app.ainvoke(initial_state, config=config)
            
            # Check if workflow was interrupted
            if "__interrupt__" in result:
                interrupt_value = result["__interrupt__"]
                
                # Handle case where interrupt_value is a list
                if isinstance(interrupt_value, list) and len(interrupt_value) > 0:
                    interrupt_value = interrupt_value[0].value if hasattr(interrupt_value[0], 'value') else interrupt_value[0]
                
                return {
                    "status": "awaiting_human_input",
                    "message": interrupt_value.get("message", "Input required"),
                    "data": interrupt_value.get("data", {
                        "type": "generic", 
                        "options": [], 
                        "instructions": "Please provide input"
                    }),
                    "thread_id": thread_id
                }
            
            # Check if workflow completed successfully
            if result.get("workflow_status") == "completed":
                return {
                    "status": "completed",
                    "thread_id": thread_id,
                    **result  # Include all workflow result data
                }
            
            # Check if there was an error
            if result.get("error_message"):
                return {
                    "status": "error",
                    "error_message": result["error_message"],
                    "thread_id": thread_id
                }
            
            # Default to completed if no specific status
            return {
                "status": "completed",
                "thread_id": thread_id,
                **result
            }
                    
        except Exception as e:
            logger.error(f"Error in workflow: {str(e)}")
            return {
                "status": "error",
                "error_message": str(e),
                "thread_id": thread_id
            }
    
    async def resume(self, user_input: str, thread_id: str) -> Dict[str, Any]:
        # Handle special commands
        if user_input.lower() == "cancel":
            return {
                "status": "cancelled", 
                "message": "Workflow cancelled by user",
                "thread_id": thread_id
            }
        
        
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            # Resume the workflow with user input using Command(resume=...)
            result = await self.app.ainvoke(
                Command(resume=user_input),
                config=config
            )
            
            # Check if workflow was interrupted again
            if "__interrupt__" in result:
                interrupt_value = result["__interrupt__"]
                
                # Handle case where interrupt_value is a list
                if isinstance(interrupt_value, list) and len(interrupt_value) > 0:
                    interrupt_value = interrupt_value[0].value if hasattr(interrupt_value[0], 'value') else interrupt_value[0]
                
                return {
                    "status": "awaiting_human_input",
                    "message": interrupt_value.get("message", "More input needed"),
                    "data": interrupt_value.get("data", {
                        "type": "generic",
                        "options": [],
                        "instructions": "Please provide input"
                    }),
                    "thread_id": thread_id
                }
            
            # Check if workflow completed successfully
            if result.get("workflow_status") == "completed":
                return {
                    "status": "completed",
                    "thread_id": thread_id,
                    **result  # Include all workflow result data
                }
            
            # Check if there was an error
            if result.get("error_message"):
                return {
                    "status": "error",
                    "error_message": result["error_message"],
                    "thread_id": thread_id
                }
            
            # Default to completed
            return {
                "status": "completed",
                "thread_id": thread_id,
                **result
            }
                    
        except Exception as e:
            logger.error(f"Error resuming workflow: {str(e)}")
            return {
                "status": "error",
                "error_message": str(e),
                "thread_id": thread_id
            }
    
    def create_interrupt(
        self, 
        message: str, 
        data: Dict[str, Any],
        validation_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
        validation_context: Optional[Dict[str, Any]] = None
    ) -> Union[Any, Dict[str, Any]]:
        """Enhanced helper method to create LangGraph-style interrupts with validation support
        
        This method supports creating interrupts with optional validation logic.
        If validation_fn is provided along with validation_input, it will:
        1. Execute the validation function with the input
        2. If validation passes, return the validation result
        3. If validation fails, create a new interrupt with guidance
        
        Args:
            message: The message to display to the human
            data: Additional data to provide context to the human
            validation_fn: Optional function to validate user input
            validation_input: Optional user input to validate
            validation_context: Optional context data needed for validation
            
        Returns:
            Either validation result (if valid) or a dict with __interrupt__ for invalid inputs
        """
        validation_input = interrupt({
            "message": message,
            "data": data
        })
        
        # Execute validation function with provided input and context
        validation_result = validation_fn(validation_input, validation_context)
        
        # Check if validation was successful
        if validation_result.get("valid", False):
            # Return the result without an interrupt
            return validation_result
        else:
            # Create a new interrupt with validation guidance
            error_message = validation_result.get("error_message", "Invalid input. Please try again.")
            guidance_data = {
                **data,  # Keep original data
                "error": True,
                "error_message": error_message,
                "previous_input": validation_input
            }
            
            # Return an interrupt with validation guidance
            return interrupt({
                "message": error_message,
                "data": guidance_data
            })
    
    def update_step(self, state: Dict, step_name: str) -> Dict:
        """Helper method to update current step"""
        state["current_step"] = step_name
        return state

    def get_interrupt_config(self, interrupt_type: str) -> Dict[str, Any]:
        """Return UI configuration for a specific interrupt type
        
        This method can be overridden by subclasses to provide custom configurations
        for their specific interrupt types.
        
        Args:
            interrupt_type: The type of interrupt
            
        Returns:
            Dict with UI configuration
        """
        # Default configuration for any interrupt type
        return {
            "emoji": "⚠️",
            "title": "Selection Required",
            "button_emoji": "",
            "max_per_row": 2,
            "utility_buttons": [
                {"text": "❌ Cancel", "data": "cancel"}
            ]
        }
