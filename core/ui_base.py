from abc import ABC, abstractmethod
from PyQt6.QtWidgets import QWidget # Use QWidget as the base Qt type

# --- Define the Combined Metaclass ---
# Combines the metaclasses of QWidget and ABC to allow multiple inheritance
class CombinedMeta(type(QWidget), type(ABC)):
    pass

# --- Define UIBase using the Combined Metaclass ---
class UIBase(ABC, metaclass=CombinedMeta): # Apply the combined metaclass
    """
    Abstract Base Class defining the interface for UI implementations (plugins and fallback)
    that provide the central content widget for the main application window.
    """
    @abstractmethod
    def get_widget(self) -> QWidget:
        """
        Returns the main QWidget instance provided by this UI implementation.
        This widget will be set as the central widget of the main application window.
        """
        pass

    @abstractmethod
    def set_data_router(self, data_router):
        """
        Provides the UI instance with a reference to the central DataRouter.
        """
        pass

    @abstractmethod
    def handle_core_event(self, event_type: str, data: dict):
        """
        Handles generic events dispatched from the core application logic.
        """
        pass