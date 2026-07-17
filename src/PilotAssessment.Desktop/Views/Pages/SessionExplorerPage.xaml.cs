using System.ComponentModel;

using Microsoft.UI.Xaml;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Views.Pages;

public sealed partial class SessionExplorerPage : Page
{
    private bool _selectionUpdate;

    public SessionExplorerPage()
    {
        ViewModel = App.Services.GetRequiredService<SessionExplorerViewModel>();
        InitializeComponent();
    }

    public SessionExplorerViewModel ViewModel { get; }

    private void OnPageLoaded(object sender, RoutedEventArgs args)
    {
        ViewModel.PropertyChanged += OnViewModelPropertyChanged;
        SynchronizeSelection();
    }

    private void OnPageUnloaded(object sender, RoutedEventArgs args) =>
        ViewModel.PropertyChanged -= OnViewModelPropertyChanged;

    private void OnViewModelPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName is nameof(SessionExplorerViewModel.SelectedSession)
            or nameof(SessionExplorerViewModel.SelectedRevision))
        {
            SynchronizeSelection();
        }
    }

    private void SynchronizeSelection()
    {
        if (_selectionUpdate)
        {
            return;
        }

        _selectionUpdate = true;
        try
        {
            SessionList.SelectedItem = ViewModel.SelectedSession;
            RevisionSelector.SelectedItem = ViewModel.SelectedRevision;
        }
        finally
        {
            _selectionUpdate = false;
        }
    }

    private async void OnSessionSelectionChanged(
        object sender,
        SelectionChangedEventArgs args)
    {
        if (_selectionUpdate || SessionList.SelectedItem is not SessionCollectionItem session)
        {
            return;
        }

        _selectionUpdate = true;
        try
        {
            await ViewModel.SelectSessionAsync(session);
            RevisionSelector.SelectedItem = ViewModel.SelectedRevision;
        }
        finally
        {
            _selectionUpdate = false;
        }
    }

    private async void OnRevisionSelectionChanged(
        object sender,
        SelectionChangedEventArgs args)
    {
        if (_selectionUpdate || RevisionSelector.SelectedItem is not SessionRevision revision)
        {
            return;
        }

        await ViewModel.SelectRevisionAsync(revision);
    }
}
