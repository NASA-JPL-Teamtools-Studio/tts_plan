"""
Example demonstrating how to plot modeled values over time.

This script shows how to:
1. Create activities with effects on modeled values
2. Compute the model profiles
3. Plot the results using the built-in plot method
"""

from datetime import datetime, timedelta
from tts_plan.activity import Activity
from tts_plan.scheduler import Scheduler
from tts_plan.modeled_values import EffectType, EffectTiming


class SimpleActivity(Activity):
    """Simple concrete activity class for examples."""
    TYPE = "SimpleActivity"
    NAME = "Simple Activity"
    DESCRIPTION = "A simple activity for examples"


class ExampleScheduler(Scheduler):
    """Example scheduler for demonstration."""
    MISSION = "EXAMPLE"
    
    def build_schedule(self):
        """Not implemented for this example."""
        pass


def main():
    """Create a schedule with modeled values and plot them."""
    
    # Create scheduler
    start_time = datetime(2026, 3, 15, 10, 0, 0)
    end_time = start_time + timedelta(hours=10)
    scheduler = ExampleScheduler(start_time=start_time, end_time=end_time)
    
    print("Creating spacecraft schedule with modeled values...")
    
    # Activity 1: Science observation (drains battery, generates data)
    observation = SimpleActivity(
        begin_time=start_time,
        duration=timedelta(hours=2),
        name="Science Observation"
    )
    observation.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -3.0)
    observation.add_effect('data_volume', EffectType.IMPULSE, EffectTiming.AT_END, 1000.0)
    scheduler.add_activity(observation)
    
    # Activity 2: Solar charging
    charging = SimpleActivity(
        begin_time=start_time + timedelta(hours=3),
        duration=timedelta(hours=2),
        name="Solar Charging"
    )
    charging.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, 8.0)
    scheduler.add_activity(charging)
    
    # Activity 3: Data downlink (drains battery, removes data)
    downlink = SimpleActivity(
        begin_time=start_time + timedelta(hours=6),
        duration=timedelta(hours=1, minutes=30),
        name="Data Downlink"
    )
    downlink.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -6.0)
    downlink.add_effect('data_volume', EffectType.CONSTANT_RATE, EffectTiming.DURING, -185.0)
    scheduler.add_activity(downlink)
    
    # Activity 4: Another observation
    observation2 = SimpleActivity(
        begin_time=start_time + timedelta(hours=8),
        duration=timedelta(hours=1, minutes=30),
        name="Science Observation 2"
    )
    observation2.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -3.5)
    observation2.add_effect('data_volume', EffectType.IMPULSE, EffectTiming.AT_END, 800.0)
    scheduler.add_activity(observation2)
    
    # Compute the model with initial values
    print("\nComputing modeled value profiles...")
    scheduler.compute_model({
        'battery_charge': 100.0,  # Start at 100 Wh
        'data_volume': 0.0        # Start with no data
    })
    
    # Print some values
    print("\nModel values at key times:")
    for activity in scheduler.activities:
        battery = scheduler.modeled_values.get_value_at_time('battery_charge', activity.end_time)
        data = scheduler.modeled_values.get_value_at_time('data_volume', activity.end_time)
        print(f"  After {activity.name}: Battery={battery:.1f} Wh, Data={data:.1f} MB")
    
    # Create plot
    print("\nGenerating plot...")
    fig = scheduler.modeled_values.plot(
        title="Spacecraft Resource Profile",
        figure_height=600,
        figure_width=1000
    )
    
    # Save to HTML file using HtmlCompiler
    try:
        from tts_html_utils.core.compiler import HtmlCompiler
        from tts_html_utils.core.components.plot import PlotBase
        from tts_html_utils.core.components.text import Heading1, Heading2, Paragraph
        
        output_file = "modeled_values_plot.html"
        compiler = HtmlCompiler(title="Spacecraft Resource Profile")
        compiler.add_body_component(Heading1("Spacecraft Resource Profile"))
        compiler.add_body_component(Paragraph(
            "This plot shows how battery charge and data volume change over time "
            "as the spacecraft executes various activities."
        ))
        compiler.add_body_component(PlotBase(fig=fig))
        compiler.render_to_file(output_file)
        print(f"\nPlot saved to: {output_file}")
    except ImportError:
        # Fallback to direct plotly HTML
        fig.write_html("modeled_values_plot.html")
        print(f"\nPlot saved to: modeled_values_plot.html")
    
    # You can also show it in a browser (uncomment to use)
    # fig.show()
    
    # Plot only battery charge
    print("\nGenerating battery-only plot...")
    battery_fig = scheduler.modeled_values.plot(
        model_names=['battery_charge'],
        title="Battery Charge Over Time",
        figure_height=400
    )
    
    try:
        battery_compiler = HtmlCompiler(title="Battery Charge Over Time")
        battery_compiler.add_body_component(Heading1("Battery Charge Over Time"))
        battery_compiler.add_body_component(PlotBase(fig=battery_fig))
        battery_compiler.render_to_file("battery_plot.html")
        print("Battery plot saved to: battery_plot.html")
    except (ImportError, NameError):
        battery_fig.write_html("battery_plot.html")
        print("Battery plot saved to: battery_plot.html")


if __name__ == "__main__":
    main()
