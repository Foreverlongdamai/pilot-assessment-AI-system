using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

using PilotAssessment.Desktop.Services.Navigation;

namespace PilotAssessment.Desktop.Views.Pages;

public sealed partial class WorkspacePlaceholderPage : Page
{
    public WorkspacePlaceholderPage()
    {
        InitializeComponent();
    }

    public string Title { get; private set; } = "Workspace";
    public string Description { get; private set; } =
        "This shell destination will be connected in the next M7B task.";

    protected override void OnNavigatedTo(NavigationEventArgs args)
    {
        base.OnNavigatedTo(args);
        if (args.Parameter is not ShellNavigationContext context)
        {
            return;
        }

        (Title, Description) = context.Destination switch
        {
            "project" => (
                "Project",
                "Create or open a managed pilot assessment project. Project commands become available after the local backend is ready."),
            "session" => (
                "Sessions",
                "Import and inspect immutable managed session revisions without embedding time-series or image payloads in the UI protocol."),
            "model" => (
                "Model Studio",
                "Design the global Raw Input, Evidence and BN graph and choose the active task scheme."),
            "runs" => (
                "Runs",
                "Preflight and start an assessment from the current autosaved task scheme."),
            "results" => (
                "Results",
                "Inspect Evidence observations, Bayesian posteriors, coverage and provenance."),
            "library" => (
                "Library",
                "Browse complete nodes, operators and reusable task schemes."),
            _ => ("Workspace", "This destination is not registered."),
        };
        Bindings.Update();
    }
}
