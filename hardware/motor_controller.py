"""
hardware/motor_controller.py - Controls the car's motors
"""

import logging
import time
import sys
import os

# Add the parent directory to the path so we can import the Freenove modules
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

logger = logging.getLogger(__name__)

class MotorController:
    """Controls the car's motors using the Freenove motor library"""
    
    def __init__(self):
        """Initialize the motor controller"""
        try:
            # Import the Motor module from the Freenove code
            # This assumes the Freenove code is available in the path
            from Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi.Code.Server.motor import Ordinary_Car
            self.motor = Ordinary_Car()
            logger.info("Motor controller initialized successfully")
        except ImportError as e:
            logger.error(f"Failed to import Freenove motor module: {e}")
            # Create a mock motor object for testing
            self.motor = MockMotor()
            logger.warning("Using mock motor controller")
    
    def set_motor_speeds(self, fl, bl, fr, br):
        """
        Set the speeds of the four motors directly
        
        Args:
            fl (int): Front left motor speed (-4056 to 4056)
            bl (int): Back left motor speed (-4056 to 4056)
            fr (int): Front right motor speed (-4056 to 4056)
            br (int): Back right motor speed (-4056 to 4056)
        """
        try:
            # Validate speed values
            fl = self._clamp_speed(fl)
            bl = self._clamp_speed(bl)
            fr = self._clamp_speed(fr)
            br = self._clamp_speed(br)
            
            # Set motor speeds
            self.motor.set_motor_model(fl, bl, fr, br)
            logger.debug(f"Set motor speeds: FL={fl}, BL={bl}, FR={fr}, BR={br}")
        except Exception as e:
            logger.error(f"Error setting motor speeds: {e}")
    
    def move_forward(self, speed=2000):
        """
        Move the car forward
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(speed, speed, speed, speed)
    
    def move_backward(self, speed=2000):
        """
        Move the car backward
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(-speed, -speed, -speed, -speed)
    
    def turn_left(self, speed=2000):
        """
        Turn the car left
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(-speed, -speed, speed, speed)
    
    def turn_right(self, speed=2000):
        """
        Turn the car right
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(speed, speed, -speed, -speed)
    
    def translate_left(self, speed=2000):
        """
        Move the car sideways to the left (mecanum wheels)
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(-speed, speed, speed, -speed)
    
    def translate_right(self, speed=2000):
        """
        Move the car sideways to the right (mecanum wheels)
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(speed, -speed, -speed, speed)
    
    def front_left_diagonal(self, speed=2000):
        """
        Move the car diagonally to the front-left (mecanum wheels)
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(0, speed, speed, 0)
    
    def front_right_diagonal(self, speed=2000):
        """
        Move the car diagonally to the front-right (mecanum wheels)
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(speed, 0, 0, speed)
    
    def rear_left_diagonal(self, speed=2000):
        """
        Move the car diagonally to the rear-left (mecanum wheels)
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(-speed, 0, 0, -speed)
    
    def rear_right_diagonal(self, speed=2000):
        """
        Move the car diagonally to the rear-right (mecanum wheels)
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(0, -speed, -speed, 0)
    
    def rotate_clockwise(self, speed=2000):
        """
        Rotate the car clockwise in place
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(speed, -speed, speed, -speed)
    
    def rotate_counterclockwise(self, speed=2000):
        """
        Rotate the car counterclockwise in place
        
        Args:
            speed (int): Speed (0-4056)
        """
        speed = self._clamp_speed(speed)
        self.set_motor_speeds(-speed, speed, -speed, speed)
    
    def stop(self):
        """Stop all motors"""
        self.set_motor_speeds(0, 0, 0, 0)
    
    def _clamp_speed(self, speed):
        """
        Clamp speed value to valid range
        
        Args:
            speed (int): Input speed
        
        Returns:
            int: Clamped speed value
        """
        return max(-4056, min(4056, speed))
    
    def close(self):
        """Close the motor controller"""
        try:
            self.stop()
            self.motor.close()
            logger.info("Motor controller closed")
        except Exception as e:
            logger.error(f"Error closing motor controller: {e}")


class MockMotor:
    """Mock motor class for testing without hardware"""
    
    def set_motor_model(self, fl, bl, fr, br):
        """Mock method for setting motor speeds"""
        logger.debug(f"[MOCK] Set motor speeds: FL={fl}, BL={bl}, FR={fr}, BR={br}")
    
    def close(self):
        """Mock method for closing the motor controller"""
        logger.debug("[MOCK] Motor controller closed")


# Example usage
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Create motor controller
    motor_ctrl = MotorController()
    
    try:
        print("Moving forward...")
        motor_ctrl.move_forward(2000)
        time.sleep(2)
        
        print("Moving backward...")
        motor_ctrl.move_backward(2000)
        time.sleep(2)
        
        print("Turning left...")
        motor_ctrl.turn_left(2000)
        time.sleep(2)
        
        print("Turning right...")
        motor_ctrl.turn_right(2000)
        time.sleep(2)
        
        print("Translating left...")
        motor_ctrl.translate_left(2000)
        time.sleep(2)
        
        print("Translating right...")
        motor_ctrl.translate_right(2000)
        time.sleep(2)
        
        print("Stopping...")
        motor_ctrl.stop()
    
    finally:
        # Clean up
        motor_ctrl.close()